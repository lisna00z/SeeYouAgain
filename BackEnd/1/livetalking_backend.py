"""
LiveTalking 后端API服务 - Windows版本
管理数字人的训练和运行
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
import psutil  # 需要安装: pip install psutil

# ==================== 配置部分 ====================
# LiveTalking项目路径
LIVETALKING_PATH = r"D:\Projects\See You Again\src\LiveTalking\LiveTalking-main"
WAV2LIP_PATH = os.path.join(LIVETALKING_PATH, "wav2lip")

# TTS服务器配置
TTS_SERVER = "http://127.0.0.1:50000"

# 文件存储路径
UPLOAD_DIR = Path("uploads")
MODELS_DIR = Path("models")
LOGS_DIR = Path("logs")

# 创建必要的目录
for dir_path in [UPLOAD_DIR, MODELS_DIR, LOGS_DIR]:
    dir_path.mkdir(exist_ok=True, parents=True)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOGS_DIR / "backend.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== FastAPI初始化 ====================
app = FastAPI(title="LiveTalking 后端API")

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
    session_id: str
    avatar_id: str  # 用户自定义的avatar ID
    video_path: str  # 上传的视频路径（由图片生成）
    audio_path: str  # 上传的音频路径
    ref_text: str   # 音频中说的话
    prompt: str     # 系统提示词

class StartRequest(BaseModel):
    session_id: str

class StopRequest(BaseModel):
    session_id: str

class ChatRequest(BaseModel):
    session_id: str
    message: str

class SessionInfo(BaseModel):
    session_id: str
    avatar_id: str
    status: str
    created_at: str
    ref_file: str
    ref_text: str
    prompt: str

# ==================== 辅助函数 ====================
def check_livetalking_installation():
    """检查LiveTalking是否正确安装"""
    if not os.path.exists(LIVETALKING_PATH):
        logger.error(f"LiveTalking路径不存在: {LIVETALKING_PATH}")
        return False
    
    app_py = os.path.join(LIVETALKING_PATH, "app.py")
    if not os.path.exists(app_py):
        logger.error(f"app.py不存在: {app_py}")
        return False
    
    genavatar_py = os.path.join(WAV2LIP_PATH, "genavatar.py")
    if not os.path.exists(genavatar_py):
        logger.error(f"genavatar.py不存在: {genavatar_py}")
        return False
    
    logger.info("LiveTalking检查通过")
    return True

def kill_process_tree(pid):
    """终止进程及其所有子进程（Windows）"""
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        
        # 先终止子进程
        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        
        # 等待子进程结束
        gone, alive = psutil.wait_procs(children, timeout=5)
        
        # 强制终止仍在运行的子进程
        for p in alive:
            try:
                p.kill()
            except psutil.NoSuchProcess:
                pass
        
        # 最后终止父进程
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

def generate_video_from_image(image_path: str, output_path: str):
    """从图片生成视频（用于训练）"""
    try:
        # 使用ffmpeg将图片转换为视频
        # 这里生成一个3秒的视频，可以根据需要调整
        cmd = [
            "ffmpeg",
            "-loop", "1",
            "-i", image_path,
            "-c:v", "libx264",
            "-t", "3",
            "-pix_fmt", "yuv420p",
            "-vf", "scale=256:256",  # wav2lip需要256x256
            "-y",  # 覆盖输出文件
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            logger.info(f"成功从图片生成视频: {output_path}")
            return True
        else:
            logger.error(f"生成视频失败: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"生成视频异常: {e}")
        return False

# ==================== API端点 ====================
@app.post("/train")
async def train_model(request: TrainRequest, background_tasks: BackgroundTasks):
    """训练数字人模型"""
    
    logger.info(f"开始训练任务: {request.session_id}")
    
    # 检查会话是否已存在
    if request.session_id in sessions and sessions[request.session_id]["status"] == "training":
        raise HTTPException(status_code=400, detail="该会话正在训练中")
    
    # 保存会话信息
    sessions[request.session_id] = {
        "session_id": request.session_id,
        "avatar_id": request.avatar_id,
        "video_path": request.video_path,
        "audio_path": request.audio_path,
        "ref_text": request.ref_text,
        "prompt": request.prompt,
        "status": "training",
        "created_at": datetime.now().isoformat(),
        "progress": 0
    }
    
    # 在后台启动训练
    background_tasks.add_task(
        run_training,
        request.session_id,
        request.avatar_id,
        request.video_path,
        request.audio_path,
        request.ref_text
    )
    
    return {
        "status": "training_started",
        "session_id": request.session_id,
        "avatar_id": request.avatar_id
    }

def run_training(session_id: str, avatar_id: str, video_path: str, audio_path: str, ref_text: str):
    """执行训练过程"""
    try:
        logger.info(f"执行训练: session={session_id}, avatar={avatar_id}")
        
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
        log_file = LOGS_DIR / f"train_{session_id}.log"
        
        # 启动训练进程
        with open(log_file, "w") as f:
            process = subprocess.Popen(
                cmd,
                stdout=f,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=WAV2LIP_PATH,
                creationflags=subprocess.CREATE_NEW_CONSOLE  # Windows: 新控制台
            )
            
            # 保存进程引用
            training_processes[session_id] = process
            
            # 等待训练完成
            return_code = process.wait(timeout=600)  # 10分钟超时
            
            if return_code == 0:
                logger.info(f"训练成功: {session_id}")
                sessions[session_id]["status"] = "ready"
                
                # 将音频文件复制到LiveTalking的wav目录
                wav_dir = os.path.join(LIVETALKING_PATH, "wav")
                os.makedirs(wav_dir, exist_ok=True)
                
                audio_filename = f"{avatar_id}.wav"
                dest_audio = os.path.join(wav_dir, audio_filename)
                shutil.copy2(audio_path, dest_audio)
                
                sessions[session_id]["ref_file"] = f"wav/{audio_filename}"
                logger.info(f"音频文件已复制到: {dest_audio}")
                
            else:
                logger.error(f"训练失败，返回码: {return_code}")
                sessions[session_id]["status"] = "error"
                sessions[session_id]["error"] = f"训练失败，返回码: {return_code}"
    
    except subprocess.TimeoutExpired:
        logger.error(f"训练超时: {session_id}")
        sessions[session_id]["status"] = "error"
        sessions[session_id]["error"] = "训练超时"
        if session_id in training_processes:
            kill_process_tree(training_processes[session_id].pid)
            del training_processes[session_id]
    
    except Exception as e:
        logger.error(f"训练异常: {e}", exc_info=True)
        sessions[session_id]["status"] = "error"
        sessions[session_id]["error"] = str(e)
    
    finally:
        # 清理进程引用
        if session_id in training_processes:
            del training_processes[session_id]
        
        # 切回原目录
        os.chdir(Path(__file__).parent)

@app.post("/start")
async def start_avatar(request: StartRequest):
    """启动数字人"""
    
    if request.session_id not in sessions:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    session = sessions[request.session_id]
    
    if session["status"] != "ready":
        raise HTTPException(status_code=400, detail=f"会话未就绪: {session['status']}")
    
    if request.session_id in running_processes:
        raise HTTPException(status_code=400, detail="该数字人已在运行")
    
    try:
        # 切换到LiveTalking主目录
        os.chdir(LIVETALKING_PATH)
        
        # 构建运行命令
        cmd = [
            "python",
            "app.py",
            "--transport", "webrtc",
            "--model", "wav2lip",
            "--avatar_id", session["avatar_id"],
            "--tts", "cosyvoice",
            "--TTS_SERVER", TTS_SERVER,
            "--REF_FILE", session["ref_file"],
            "--REF_TEXT", session["ref_text"]
        ]
        
        logger.info(f"启动命令: {' '.join(cmd)}")
        
        # 创建日志文件
        log_file = LOGS_DIR / f"run_{request.session_id}.log"
        
        # 启动进程
        with open(log_file, "w") as f:
            process = subprocess.Popen(
                cmd,
                stdout=f,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=LIVETALKING_PATH,
                creationflags=subprocess.CREATE_NEW_CONSOLE  # Windows: 新控制台
            )
        
        # 保存进程引用
        running_processes[request.session_id] = process
        
        # 更新会话状态
        session["status"] = "running"
        session["pid"] = process.pid
        
        # 等待一下确保进程启动
        time.sleep(2)
        
        # 检查进程是否仍在运行
        if process.poll() is not None:
            del running_processes[request.session_id]
            session["status"] = "error"
            raise HTTPException(status_code=500, detail="启动失败，进程已退出")
        
        logger.info(f"成功启动数字人: {request.session_id}, PID: {process.pid}")
        
        return {
            "status": "started",
            "session_id": request.session_id,
            "pid": process.pid,
            "webrtc_url": "http://localhost:8010"  # LiveTalking的WebRTC地址
        }
    
    except Exception as e:
        logger.error(f"启动失败: {e}", exc_info=True)
        session["status"] = "error"
        raise HTTPException(status_code=500, detail=f"启动失败: {e}")
    
    finally:
        # 切回原目录
        os.chdir(Path(__file__).parent)

@app.post("/stop")
async def stop_avatar(request: StopRequest):
    """停止数字人"""
    
    if request.session_id not in running_processes:
        return {"status": "not_running", "message": "该数字人未在运行"}
    
    try:
        process = running_processes[request.session_id]
        pid = process.pid
        
        # 终止进程树
        kill_process_tree(pid)
        
        # 清理进程引用
        del running_processes[request.session_id]
        
        # 更新会话状态
        if request.session_id in sessions:
            sessions[request.session_id]["status"] = "ready"
            if "pid" in sessions[request.session_id]:
                del sessions[request.session_id]["pid"]
        
        logger.info(f"成功停止数字人: {request.session_id}")
        
        return {
            "status": "stopped",
            "session_id": request.session_id,
            "pid": pid
        }
    
    except Exception as e:
        logger.error(f"停止失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"停止失败: {e}")

@app.post("/chat")
async def chat_with_avatar(request: ChatRequest):
    """与数字人对话（消息会通过WebRTC传输）"""
    
    if request.session_id not in sessions:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    if request.session_id not in running_processes:
        raise HTTPException(status_code=400, detail="数字人未运行")
    
    # 检查进程是否仍在运行
    process = running_processes[request.session_id]
    if process.poll() is not None:
        del running_processes[request.session_id]
        sessions[request.session_id]["status"] = "error"
        raise HTTPException(status_code=400, detail="数字人进程已退出")
    
    # 注意：实际的对话通过WebRTC在前端直接与LiveTalking通信
    # 这里只返回确认信息
    return {
        "status": "success",
        "message": "消息已接收，请通过WebRTC查看数字人回应",
        "webrtc_url": "http://localhost:8010"
    }

@app.get("/sessions")
async def list_sessions():
    """列出所有会话"""
    return {
        "sessions": list(sessions.values()),
        "total": len(sessions)
    }

@app.get("/session/{session_id}")
async def get_session(session_id: str):
    """获取会话详情"""
    
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    session = sessions[session_id].copy()
    
    # 检查进程状态
    if session_id in running_processes:
        process = running_processes[session_id]
        if process.poll() is None:
            session["is_running"] = True
            session["pid"] = process.pid
        else:
            session["is_running"] = False
            del running_processes[session_id]
    else:
        session["is_running"] = False
    
    return session

@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """删除会话"""
    
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    # 如果正在运行，先停止
    if session_id in running_processes:
        await stop_avatar(StopRequest(session_id=session_id))
    
    # 如果正在训练，终止训练
    if session_id in training_processes:
        kill_process_tree(training_processes[session_id].pid)
        del training_processes[session_id]
    
    # 删除会话信息
    del sessions[session_id]
    
    logger.info(f"删除会话: {session_id}")
    
    return {"status": "deleted", "session_id": session_id}

@app.post("/upload/image")
async def upload_image(file: UploadFile = File(...)):
    """上传图片并生成训练用视频"""
    
    # 生成唯一文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{file.filename}"
    
    # 保存图片
    image_path = UPLOAD_DIR / filename
    with open(image_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    # 生成视频
    video_filename = f"{timestamp}_generated.mp4"
    video_path = UPLOAD_DIR / video_filename
    
    if not generate_video_from_image(str(image_path), str(video_path)):
        raise HTTPException(status_code=500, detail="生成视频失败")
    
    return {
        "image_path": str(image_path),
        "video_path": str(video_path),
        "filename": filename
    }

@app.post("/upload/audio")
async def upload_audio(file: UploadFile = File(...)):
    """上传音频文件"""
    
    # 生成唯一文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{file.filename}"
    
    # 保存音频
    audio_path = UPLOAD_DIR / filename
    with open(audio_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    return {
        "audio_path": str(audio_path),
        "filename": filename
    }

@app.get("/health")
async def health_check():
    """健康检查"""
    
    livetalking_ok = check_livetalking_installation()
    
    return {
        "status": "healthy" if livetalking_ok else "degraded",
        "livetalking": livetalking_ok,
        "sessions": len(sessions),
        "running": len(running_processes),
        "training": len(training_processes)
    }

@app.on_event("shutdown")
async def shutdown_event():
    """关闭时清理所有进程"""
    logger.info("正在关闭所有运行中的进程...")
    
    # 停止所有运行中的数字人
    for session_id, process in list(running_processes.items()):
        try:
            kill_process_tree(process.pid)
        except:
            pass
    
    # 停止所有训练进程
    for session_id, process in list(training_processes.items()):
        try:
            kill_process_tree(process.pid)
        except:
            pass
    
    logger.info("所有进程已清理")

if __name__ == "__main__":
    # 检查LiveTalking安装
    if not check_livetalking_installation():
        logger.error("LiveTalking未正确安装，请检查路径配置")
        exit(1)
    
    # 启动服务器
    logger.info("启动LiveTalking后端服务...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=False  # 生产环境设为False
    )
