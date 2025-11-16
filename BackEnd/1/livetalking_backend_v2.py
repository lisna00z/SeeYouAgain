"""
LiveTalking 后端API服务 - 改进版
支持视频上传、自动扫描已有数字人、自动移动训练结果
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, File, UploadFile
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import subprocess
import threading
import json
import os
import time
import asyncio
import logging
from typing import Dict, Optional, List
from pathlib import Path
import signal
import shutil
from datetime import datetime
import psutil

# ==================== 配置部分 ====================
# LiveTalking项目路径
LIVETALKING_PATH = r"D:\Projects\See You Again\src\LiveTalking\LiveTalking-main"
WAV2LIP_PATH = os.path.join(LIVETALKING_PATH, "wav2lip")

# 重要目录
AVATARS_DIR = os.path.join(LIVETALKING_PATH, "data", "avatars")  # 可用的数字人
RESULTS_DIR = os.path.join(WAV2LIP_PATH, "results", "avatars")  # 训练结果输出
WAV_DIR = os.path.join(LIVETALKING_PATH, "wav")  # 音频文件目录

# TTS服务器配置
TTS_SERVER = "http://127.0.0.1:50000"

# 文件存储路径
UPLOAD_DIR = Path("uploads")
LOGS_DIR = Path("logs")

# 创建必要的目录
for dir_path in [UPLOAD_DIR, LOGS_DIR]:
    dir_path.mkdir(exist_ok=True, parents=True)

# 确保LiveTalking的目录存在
os.makedirs(AVATARS_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(WAV_DIR, exist_ok=True)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOGS_DIR / "backend.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== FastAPI初始化 ====================
app = FastAPI(title="LiveTalking 后端API - 改进版")

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== 全局变量 ====================
# 存储会话信息
sessions: Dict[str, dict] = {}

# 存储运行中的进程
running_processes: Dict[str, subprocess.Popen] = {}

# 存储训练中的进程
training_processes: Dict[str, subprocess.Popen] = {}

# ==================== 数据模型 ====================
class TrainRequest(BaseModel):
    avatar_id: str  # 用户自定义的avatar ID
    video_path: str  # 上传的MP4视频路径
    audio_path: str  # 上传的WAV音频路径
    ref_text: str   # 音频中说的话
    prompt: str     # 系统提示词

class StartRequest(BaseModel):
    avatar_id: str  # 使用完整的avatar ID，如 wav2lip256_avatarMan

class StopRequest(BaseModel):
    avatar_id: str

class ChatRequest(BaseModel):
    avatar_id: str
    message: str

# ==================== 辅助函数 ====================
def scan_existing_avatars() -> List[str]:
    """扫描已有的数字人"""
    avatars = []
    
    if os.path.exists(AVATARS_DIR):
        for item in os.listdir(AVATARS_DIR):
            item_path = os.path.join(AVATARS_DIR, item)
            if os.path.isdir(item_path) and item.startswith("wav2lip256_"):
                avatars.append(item)
                logger.info(f"发现数字人: {item}")
    
    return avatars

def check_avatar_exists(avatar_id: str) -> bool:
    """检查数字人是否存在"""
    avatar_path = os.path.join(AVATARS_DIR, avatar_id)
    return os.path.exists(avatar_path)

def move_trained_avatar(avatar_id: str) -> bool:
    """将训练好的数字人从results移动到data/avatars"""
    source_path = os.path.join(RESULTS_DIR, avatar_id)
    dest_path = os.path.join(AVATARS_DIR, avatar_id)
    
    try:
        if os.path.exists(source_path):
            # 如果目标已存在，先备份
            if os.path.exists(dest_path):
                backup_path = f"{dest_path}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.move(dest_path, backup_path)
                logger.info(f"已备份原数字人到: {backup_path}")
            
            # 移动文件夹
            shutil.move(source_path, dest_path)
            logger.info(f"成功移动数字人: {avatar_id}")
            logger.info(f"从: {source_path}")
            logger.info(f"到: {dest_path}")
            return True
        else:
            logger.warning(f"训练结果不存在: {source_path}")
            return False
    except Exception as e:
        logger.error(f"移动数字人失败: {e}")
        return False

def kill_process_tree(pid):
    """终止进程及其所有子进程（Windows）"""
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        
        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        
        gone, alive = psutil.wait_procs(children, timeout=5)
        
        for p in alive:
            try:
                p.kill()
            except psutil.NoSuchProcess:
                pass
        
        try:
            parent.terminate()
            parent.wait(timeout=5)
        except (psutil.NoSuchProcess, psutil.TimeoutExpired):
            try:
                parent.kill()
            except psutil.NoSuchProcess:
                pass
        
        logger.info(f"成功终止进程树 PID: {pid}")
    except Exception as e:
        logger.error(f"终止进程树失败 PID {pid}: {e}")

# ==================== API端点 ====================
@app.get("/avatars")
async def list_avatars():
    """获取所有可用的数字人"""
    avatars = scan_existing_avatars()
    
    # 获取每个数字人的状态
    avatar_info = []
    for avatar_id in avatars:
        info = {
            "avatar_id": avatar_id,
            "name": avatar_id.replace("wav2lip256_", ""),
            "status": "ready",
            "is_running": False
        }
        
        # 检查是否正在运行
        if avatar_id in running_processes:
            process = running_processes[avatar_id]
            if process.poll() is None:
                info["status"] = "running"
                info["is_running"] = True
                info["pid"] = process.pid
        
        # 检查是否正在训练
        if avatar_id in training_processes:
            process = training_processes[avatar_id]
            if process.poll() is None:
                info["status"] = "training"
        
        avatar_info.append(info)
    
    return {
        "avatars": avatar_info,
        "total": len(avatar_info)
    }

@app.post("/train")
async def train_model(request: TrainRequest, background_tasks: BackgroundTasks):
    """训练数字人模型"""
    
    logger.info(f"开始训练任务: {request.avatar_id}")
    
    # 构建完整的avatar_id
    if not request.avatar_id.startswith("wav2lip256_"):
        full_avatar_id = f"wav2lip256_{request.avatar_id}"
    else:
        full_avatar_id = request.avatar_id
    
    # 检查是否已在训练
    if full_avatar_id in training_processes:
        process = training_processes[full_avatar_id]
        if process.poll() is None:
            raise HTTPException(status_code=400, detail="该数字人正在训练中")
    
    # 保存会话信息
    sessions[full_avatar_id] = {
        "avatar_id": full_avatar_id,
        "video_path": request.video_path,
        "audio_path": request.audio_path,
        "ref_text": request.ref_text,
        "prompt": request.prompt,
        "status": "training",
        "created_at": datetime.now().isoformat()
    }
    
    # 在后台启动训练
    background_tasks.add_task(
        run_training,
        full_avatar_id,
        request.video_path,
        request.audio_path,
        request.ref_text
    )
    
    return {
        "status": "training_started",
        "avatar_id": full_avatar_id,
        "message": f"开始训练 {full_avatar_id}"
    }

def run_training(avatar_id: str, video_path: str, audio_path: str, ref_text: str):
    """执行训练过程"""
    try:
        logger.info(f"执行训练: avatar={avatar_id}")
        
        sessions[avatar_id]["status"] = "training"
        
        # 切换到wav2lip目录
        os.chdir(WAV2LIP_PATH)
        
        # 构建训练命令
        cmd = [
            "python",
            "genavatar.py",
            "--video_path", video_path,
            "--img_size", "256",
            "--avatar_id", avatar_id
        ]
        
        logger.info(f"训练命令: {' '.join(cmd)}")
        
        # 创建日志文件
        log_file = LOGS_DIR / f"train_{avatar_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        # 启动训练进程
        with open(log_file, "w", encoding='utf-8') as f:
            process = subprocess.Popen(
                cmd,
                stdout=f,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=WAV2LIP_PATH,
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            
            training_processes[avatar_id] = process
            
            # 等待训练完成
            return_code = process.wait(timeout=1200)  # 20分钟超时
            
            if return_code == 0:
                logger.info(f"训练成功: {avatar_id}")
                
                # 移动训练结果到data/avatars
                if move_trained_avatar(avatar_id):
                    sessions[avatar_id]["status"] = "ready"
                    
                    # 复制音频文件到wav目录
                    audio_filename = f"{avatar_id}.wav"
                    dest_audio = os.path.join(WAV_DIR, audio_filename)
                    shutil.copy2(audio_path, dest_audio)
                    sessions[avatar_id]["ref_file"] = f"wav/{audio_filename}"
                    logger.info(f"音频文件已复制到: {dest_audio}")
                else:
                    sessions[avatar_id]["status"] = "error"
                    sessions[avatar_id]["error"] = "无法移动训练结果"
            else:
                logger.error(f"训练失败，返回码: {return_code}")
                sessions[avatar_id]["status"] = "error"
                sessions[avatar_id]["error"] = f"训练失败，返回码: {return_code}"
    
    except subprocess.TimeoutExpired:
        logger.error(f"训练超时: {avatar_id}")
        sessions[avatar_id]["status"] = "error"
        sessions[avatar_id]["error"] = "训练超时"
        if avatar_id in training_processes:
            kill_process_tree(training_processes[avatar_id].pid)
    
    except Exception as e:
        logger.error(f"训练异常: {e}", exc_info=True)
        sessions[avatar_id]["status"] = "error"
        sessions[avatar_id]["error"] = str(e)
    
    finally:
        if avatar_id in training_processes:
            del training_processes[avatar_id]
        os.chdir(Path(__file__).parent)

@app.post("/start")
async def start_avatar(request: StartRequest):
    """启动数字人"""
    
    avatar_id = request.avatar_id
    
    # 检查数字人是否存在
    if not check_avatar_exists(avatar_id):
        raise HTTPException(status_code=404, detail=f"数字人不存在: {avatar_id}")
    
    # 检查是否已在运行
    if avatar_id in running_processes:
        process = running_processes[avatar_id]
        if process.poll() is None:
            raise HTTPException(status_code=400, detail="该数字人已在运行")
    
    try:
        os.chdir(LIVETALKING_PATH)
        
        # 获取音频文件和参考文本
        ref_file = f"wav/{avatar_id}.wav"
        ref_text = sessions.get(avatar_id, {}).get("ref_text", "Hello, I am a digital avatar.")
        
        # 检查音频文件是否存在
        audio_path = os.path.join(LIVETALKING_PATH, ref_file)
        if not os.path.exists(audio_path):
            # 尝试查找任何可用的音频文件
            wav_files = [f for f in os.listdir(WAV_DIR) if f.endswith('.wav')]
            if wav_files:
                ref_file = f"wav/{wav_files[0]}"
                logger.warning(f"使用默认音频: {ref_file}")
            else:
                logger.warning("没有找到参考音频文件")
                ref_file = "wav/default.wav"  # 假设有默认音频
        
        # 构建运行命令
        cmd = [
            "python",
            "app.py",
            "--transport", "webrtc",
            "--model", "wav2lip",
            "--avatar_id", avatar_id,
            "--tts", "cosyvoice",
            "--TTS_SERVER", TTS_SERVER,
            "--REF_FILE", ref_file,
            "--REF_TEXT", ref_text
        ]
        
        logger.info(f"启动命令: {' '.join(cmd)}")
        
        # 创建日志文件
        log_file = LOGS_DIR / f"run_{avatar_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        # 启动进程
        with open(log_file, "w", encoding='utf-8') as f:
            process = subprocess.Popen(
                cmd,
                stdout=f,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=LIVETALKING_PATH,
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
        
        running_processes[avatar_id] = process
        
        # 更新状态
        if avatar_id not in sessions:
            sessions[avatar_id] = {}
        sessions[avatar_id]["status"] = "running"
        sessions[avatar_id]["pid"] = process.pid
        
        time.sleep(2)
        
        if process.poll() is not None:
            del running_processes[avatar_id]
            sessions[avatar_id]["status"] = "error"
            raise HTTPException(status_code=500, detail="启动失败，进程已退出")
        
        logger.info(f"成功启动数字人: {avatar_id}, PID: {process.pid}")
        
        return {
            "status": "started",
            "avatar_id": avatar_id,
            "pid": process.pid,
            "webrtc_url": "http://localhost:8010"
        }
    
    except Exception as e:
        logger.error(f"启动失败: {e}", exc_info=True)
        if avatar_id in sessions:
            sessions[avatar_id]["status"] = "error"
        raise HTTPException(status_code=500, detail=f"启动失败: {e}")
    
    finally:
        os.chdir(Path(__file__).parent)

@app.post("/stop")
async def stop_avatar(request: StopRequest):
    """停止数字人"""
    
    avatar_id = request.avatar_id
    
    if avatar_id not in running_processes:
        return {"status": "not_running", "message": "该数字人未在运行"}
    
    try:
        process = running_processes[avatar_id]
        pid = process.pid
        
        kill_process_tree(pid)
        del running_processes[avatar_id]
        
        if avatar_id in sessions:
            sessions[avatar_id]["status"] = "ready"
            if "pid" in sessions[avatar_id]:
                del sessions[avatar_id]["pid"]
        
        logger.info(f"成功停止数字人: {avatar_id}")
        
        return {
            "status": "stopped",
            "avatar_id": avatar_id,
            "pid": pid
        }
    
    except Exception as e:
        logger.error(f"停止失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"停止失败: {e}")

@app.post("/upload/video")
async def upload_video(file: UploadFile = File(...)):
    """上传MP4视频文件"""
    
    # 检查文件格式
    if not file.filename.lower().endswith('.mp4'):
        raise HTTPException(status_code=400, detail="只支持MP4格式的视频")
    
    # 生成唯一文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{file.filename}"
    
    # 保存视频
    video_path = UPLOAD_DIR / filename
    with open(video_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    logger.info(f"视频上传成功: {video_path}")
    
    return {
        "video_path": str(video_path),
        "filename": filename
    }

@app.post("/upload/audio")
async def upload_audio(file: UploadFile = File(...)):
    """上传WAV音频文件"""
    
    # 检查文件格式
    if not file.filename.lower().endswith('.wav'):
        raise HTTPException(status_code=400, detail="只支持WAV格式的音频")
    
    # 生成唯一文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{file.filename}"
    
    # 保存音频
    audio_path = UPLOAD_DIR / filename
    with open(audio_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    logger.info(f"音频上传成功: {audio_path}")
    
    return {
        "audio_path": str(audio_path),
        "filename": filename
    }

@app.get("/training-status/{avatar_id}")
async def get_training_status(avatar_id: str):
    """获取训练状态"""
    
    if avatar_id in sessions:
        return sessions[avatar_id]
    
    # 检查是否是已存在的数字人
    if check_avatar_exists(avatar_id):
        return {
            "avatar_id": avatar_id,
            "status": "ready",
            "exists": True
        }
    
    return {
        "avatar_id": avatar_id,
        "status": "not_found",
        "exists": False
    }

@app.get("/health")
async def health_check():
    """健康检查"""
    
    return {
        "status": "healthy",
        "livetalking_path": LIVETALKING_PATH,
        "avatars_dir": os.path.exists(AVATARS_DIR),
        "results_dir": os.path.exists(RESULTS_DIR),
        "total_avatars": len(scan_existing_avatars()),
        "running": len(running_processes),
        "training": len(training_processes)
    }

@app.on_event("shutdown")
async def shutdown_event():
    """关闭时清理所有进程"""
    logger.info("正在关闭所有运行中的进程...")
    
    for avatar_id, process in list(running_processes.items()):
        try:
            kill_process_tree(process.pid)
        except:
            pass
    
    for avatar_id, process in list(training_processes.items()):
        try:
            kill_process_tree(process.pid)
        except:
            pass
    
    logger.info("所有进程已清理")

if __name__ == "__main__":
    logger.info(f"LiveTalking路径: {LIVETALKING_PATH}")
    logger.info(f"数字人目录: {AVATARS_DIR}")
    logger.info(f"训练结果目录: {RESULTS_DIR}")
    
    # 扫描现有数字人
    existing_avatars = scan_existing_avatars()
    logger.info(f"发现 {len(existing_avatars)} 个数字人: {existing_avatars}")
    
    # 启动服务器
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=False
    )
