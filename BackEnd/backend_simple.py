"""
LiveTalking 后端API服务 - 简化稳定版
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import subprocess
import os
import time
import shutil
import logging
from typing import Dict, List
from pathlib import Path
from datetime import datetime
import psutil

# ==================== 配置 ====================
# LiveTalking项目路径
LIVETALKING_PATH = r"D:\Projects\See You Again\src\LiveTalking\LiveTalking-main"

# 关键目录
AVATARS_DIR = os.path.join(LIVETALKING_PATH, "data", "avatars")
RESULTS_DIR = os.path.join(LIVETALKING_PATH, "wav2lip", "results", "avatars")
WAV_DIR = os.path.join(LIVETALKING_PATH, "wav")
WAV2LIP_DIR = os.path.join(LIVETALKING_PATH, "wav2lip")

# 本地目录
UPLOAD_DIR = Path("uploads")
LOGS_DIR = Path("logs")

# 创建本地目录
UPLOAD_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== FastAPI ====================
app = FastAPI(title="LiveTalking Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== 全局变量 ====================
# 运行中的进程
running_processes: Dict[str, subprocess.Popen] = {}

# 训练状态
training_status: Dict[str, str] = {}

# ==================== 数据模型 ====================
class StartRequest(BaseModel):
    avatar_id: str
    ref_file: str  # 音频文件路径
    ref_text: str  # 音频文本

class TrainRequest(BaseModel):
    avatar_id: str
    video_path: str
    audio_path: str
    ref_text: str

# ==================== 工具函数 ====================
def scan_avatars() -> List[Dict]:
    """扫描已有数字人"""
    avatars = []
    
    if os.path.exists(AVATARS_DIR):
        for item in os.listdir(AVATARS_DIR):
            if item.startswith("wav2lip256_"):
                avatar_path = os.path.join(AVATARS_DIR, item)
                if os.path.isdir(avatar_path):
                    # 检查对应的音频文件
                    wav_file = os.path.join(WAV_DIR, f"{item}.wav")
                    has_audio = os.path.exists(wav_file)
                    
                    avatars.append({
                        "id": item,
                        "name": item.replace("wav2lip256_", ""),
                        "path": avatar_path,
                        "has_audio": has_audio,
                        "is_running": item in running_processes
                    })
    
    logger.info(f"扫描到 {len(avatars)} 个数字人")
    return avatars

def kill_process(pid):
    """终止进程"""
    try:
        process = psutil.Process(pid)
        process.terminate()
        process.wait(timeout=5)
    except:
        try:
            process = psutil.Process(pid)
            process.kill()
        except:
            pass

# ==================== API端点 ====================
@app.get("/avatars")
async def get_avatars():
    """获取所有数字人"""
    return {"avatars": scan_avatars()}

@app.post("/start")
async def start_avatar(request: StartRequest):
    """启动数字人"""
    avatar_id = request.avatar_id
    
    # 检查数字人是否存在
    avatar_path = os.path.join(AVATARS_DIR, avatar_id)
    if not os.path.exists(avatar_path):
        raise HTTPException(status_code=404, detail=f"数字人不存在: {avatar_id}")
    
    # 检查是否已运行
    if avatar_id in running_processes:
        if running_processes[avatar_id].poll() is None:
            raise HTTPException(status_code=400, detail="该数字人已在运行")
    
    try:
        # 构建命令
        cmd = [
            "python",
            os.path.join(LIVETALKING_PATH, "app.py"),
            "--transport", "webrtc",
            "--model", "wav2lip",
            "--avatar_id", avatar_id,
            "--tts", "cosyvoice",
            "--TTS_SERVER", "http://127.0.0.1:50000",
            "--REF_FILE", request.ref_file,
            "--REF_TEXT", request.ref_text
        ]
        
        logger.info(f"启动命令: {' '.join(cmd)}")
        
        # 启动进程
        process = subprocess.Popen(
            cmd,
            cwd=LIVETALKING_PATH,
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        
        running_processes[avatar_id] = process
        
        # 等待确认启动
        time.sleep(3)
        
        if process.poll() is not None:
            del running_processes[avatar_id]
            raise HTTPException(status_code=500, detail="启动失败")
        
        return {
            "status": "running",
            "pid": process.pid,
            "avatar_id": avatar_id
        }
        
    except Exception as e:
        logger.error(f"启动失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/stop/{avatar_id}")
async def stop_avatar(avatar_id: str):
    """停止数字人"""
    if avatar_id not in running_processes:
        return {"status": "not_running"}
    
    process = running_processes[avatar_id]
    if process.poll() is None:
        kill_process(process.pid)
    
    del running_processes[avatar_id]
    return {"status": "stopped"}

@app.post("/train")
async def train_avatar(request: TrainRequest, background: BackgroundTasks):
    """训练数字人"""
    
    # 生成完整ID
    if not request.avatar_id.startswith("wav2lip256_"):
        avatar_id = f"wav2lip256_{request.avatar_id}"
    else:
        avatar_id = request.avatar_id
    
    training_status[avatar_id] = "training"
    
    # 添加后台任务
    background.add_task(run_training, avatar_id, request.video_path, request.audio_path, request.ref_text)
    
    return {
        "status": "training_started",
        "avatar_id": avatar_id
    }

def run_training(avatar_id: str, video_path: str, audio_path: str, ref_text: str):
    """执行训练"""
    try:
        logger.info(f"开始训练: {avatar_id}")
        
        # 构建命令
        cmd = [
            "python",
            "genavatar.py",
            "--video_path", video_path,
            "--img_size", "256",
            "--avatar_id", avatar_id
        ]
        
        # 执行训练
        result = subprocess.run(
            cmd,
            cwd=WAV2LIP_DIR,
            capture_output=True,
            text=True,
            timeout=1800  # 30分钟超时
        )
        
        if result.returncode == 0:
            # 移动结果
            source = os.path.join(RESULTS_DIR, avatar_id)
            dest = os.path.join(AVATARS_DIR, avatar_id)
            
            if os.path.exists(source):
                if os.path.exists(dest):
                    shutil.rmtree(dest)
                shutil.move(source, dest)
                
                # 复制音频
                wav_dest = os.path.join(WAV_DIR, f"{avatar_id}.wav")
                shutil.copy2(audio_path, wav_dest)
                
                training_status[avatar_id] = "completed"
                logger.info(f"训练完成: {avatar_id}")
            else:
                training_status[avatar_id] = "error"
                logger.error(f"训练结果不存在: {source}")
        else:
            training_status[avatar_id] = "error"
            logger.error(f"训练失败: {result.stderr}")
            
    except Exception as e:
        training_status[avatar_id] = "error"
        logger.error(f"训练异常: {e}")

@app.get("/training/{avatar_id}")
async def get_training_status(avatar_id: str):
    """获取训练状态"""
    return {
        "avatar_id": avatar_id,
        "status": training_status.get(avatar_id, "unknown")
    }

@app.post("/upload/video")
async def upload_video(file: UploadFile = File(...)):
    """上传视频"""
    if not file.filename.lower().endswith('.mp4'):
        raise HTTPException(status_code=400, detail="只支持MP4格式")
    
    filepath = UPLOAD_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
    
    with open(filepath, "wb") as f:
        content = await file.read()
        f.write(content)
    
    return {"path": str(filepath)}

@app.post("/upload/audio")
async def upload_audio(file: UploadFile = File(...)):
    """上传音频"""
    if not file.filename.lower().endswith('.wav'):
        raise HTTPException(status_code=400, detail="只支持WAV格式")
    
    filepath = UPLOAD_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
    
    with open(filepath, "wb") as f:
        content = await file.read()
        f.write(content)
    
    return {"path": str(filepath)}

@app.get("/health")
async def health():
    """健康检查"""
    return {
        "status": "ok",
        "avatars_count": len(scan_avatars()),
        "running_count": len(running_processes),
        "training_count": len([s for s in training_status.values() if s == "training"])
    }

@app.on_event("shutdown")
async def shutdown():
    """关闭时清理"""
    for avatar_id, process in running_processes.items():
        if process.poll() is None:
            kill_process(process.pid)

if __name__ == "__main__":
    logger.info("启动 LiveTalking 后端服务...")
    logger.info(f"数字人目录: {AVATARS_DIR}")
    logger.info(f"已有数字人: {[a['name'] for a in scan_avatars()]}")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
