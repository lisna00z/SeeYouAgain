import gradio as gr
import requests
import json
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import os

# ========== 配置 ==========
BACKEND_API = "http://localhost:8000"
WEBRTC_URL = "http://localhost:8010"

class DigitalHumanManager:
    """数字人管理器"""
    def __init__(self):
        self.avatars: Dict[str, dict] = {}
        self.current_avatar_id = None
        self.refresh_avatars()
    
    def refresh_avatars(self) -> List[str]:
        """从后端刷新数字人列表"""
        try:
            response = requests.get(f"{BACKEND_API}/avatars")
            if response.status_code == 200:
                data = response.json()
                self.avatars = {}
                avatar_list = []
                
                for avatar_info in data["avatars"]:
                    avatar_id = avatar_info["avatar_id"]
                    self.avatars[avatar_id] = avatar_info
                    
                    # 构建显示名称
                    status_emoji = {
                        "ready": "✅",
                        "running": "▶️",
                        "training": "🔄",
                        "error": "❌"
                    }.get(avatar_info["status"], "❓")
                    
                    display_name = f"{status_emoji} {avatar_info['name']}"
                    avatar_list.append((avatar_id, display_name))
                
                return avatar_list
        except Exception as e:
            print(f"刷新数字人列表失败: {e}")
            return []
    
    def get_avatar_info(self, avatar_id: str) -> dict:
        """获取数字人信息"""
        if avatar_id in self.avatars:
            return self.avatars[avatar_id]
        
        # 尝试从后端获取
        try:
            response = requests.get(f"{BACKEND_API}/training-status/{avatar_id}")
            if response.status_code == 200:
                return response.json()
        except:
            pass
        
        return {"status": "unknown"}

# 创建全局管理器
manager = DigitalHumanManager()

# ========== 主要功能函数 ==========
def create_or_train_avatar(
    action: str,
    avatar_name: str,
    video_file: str,
    audio_file: str,
    ref_text: str,
    prompt: str
) -> Tuple[gr.Dropdown, str, str]:
    """创建新数字人或训练现有数字人"""
    
    if action == "选择现有数字人":
        return refresh_avatar_list(), "请从下拉菜单选择一个数字人", ""
    
    # 创建新数字人
    if not all([avatar_name, video_file, audio_file, ref_text]):
        return gr.Dropdown(choices=manager.refresh_avatars()), "❌ 请填写所有必填字段", ""
    
    # 验证文件格式
    if not video_file.lower().endswith('.mp4'):
        return gr.Dropdown(choices=manager.refresh_avatars()), "❌ 视频必须是MP4格式", ""
    
    if not audio_file.lower().endswith('.wav'):
        return gr.Dropdown(choices=manager.refresh_avatars()), "❌ 音频必须是WAV格式", ""
    
    try:
        # 1. 上传视频
        with open(video_file, "rb") as f:
            response = requests.post(
                f"{BACKEND_API}/upload/video",
                files={"file": (os.path.basename(video_file), f, "video/mp4")}
            )
        
        if response.status_code != 200:
            error_msg = response.json().get("detail", "视频上传失败")
            return gr.Dropdown(choices=manager.refresh_avatars()), f"❌ {error_msg}", ""
        
        video_data = response.json()
        video_path = video_data["video_path"]
        
        # 2. 上传音频
        with open(audio_file, "rb") as f:
            response = requests.post(
                f"{BACKEND_API}/upload/audio",
                files={"file": (os.path.basename(audio_file), f, "audio/wav")}
            )
        
        if response.status_code != 200:
            error_msg = response.json().get("detail", "音频上传失败")
            return gr.Dropdown(choices=manager.refresh_avatars()), f"❌ {error_msg}", ""
        
        audio_data = response.json()
        audio_path = audio_data["audio_path"]
        
        # 3. 发送训练请求
        train_data = {
            "avatar_id": avatar_name,  # 不需要wav2lip256_前缀，后端会添加
            "video_path": video_path,
            "audio_path": audio_path,
            "ref_text": ref_text,
            "prompt": prompt or "你是一个友好的数字助手"
        }
        
        response = requests.post(f"{BACKEND_API}/train", json=train_data)
        
        if response.status_code != 200:
            error_msg = response.json().get("detail", "训练请求失败")
            return gr.Dropdown(choices=manager.refresh_avatars()), f"❌ {error_msg}", ""
        
        result = response.json()
        avatar_id = result["avatar_id"]
        
        # 启动状态监控
        threading.Thread(target=monitor_training, args=(avatar_id,), daemon=True).start()
        
        return (
            gr.Dropdown(choices=manager.refresh_avatars()),
            f"✅ 开始训练 {avatar_id}！预计需要10-20分钟...",
            ""
        )
        
    except Exception as e:
        return gr.Dropdown(choices=manager.refresh_avatars()), f"❌ 错误: {str(e)}", ""

def monitor_training(avatar_id: str):
    """监控训练状态"""
    while True:
        try:
            response = requests.get(f"{BACKEND_API}/training-status/{avatar_id}")
            if response.status_code == 200:
                data = response.json()
                status = data.get("status", "unknown")
                
                if status == "ready":
                    print(f"✅ 训练完成: {avatar_id}")
                    manager.refresh_avatars()
                    break
                elif status == "error":
                    print(f"❌ 训练失败: {avatar_id}")
                    if "error" in data:
                        print(f"错误: {data['error']}")
                    break
                elif status != "training":
                    break
        except:
            pass
        
        time.sleep(10)  # 每10秒检查一次

def select_avatar(avatar_dropdown: str) -> Tuple[str, str, str]:
    """选择数字人"""
    if not avatar_dropdown:
        return "请选择一个数字人", "▶️ 启动", ""
    
    manager.current_avatar_id = avatar_dropdown
    avatar_info = manager.get_avatar_info(avatar_dropdown)
    
    status_info = f"""
数字人ID: {avatar_dropdown}
名称: {avatar_info.get('name', avatar_dropdown)}
状态: {avatar_info.get('status', 'unknown')}
"""
    
    if avatar_info.get('is_running'):
        status_info += f"进程PID: {avatar_info.get('pid', 'N/A')}\n"
        btn_text = "⏸️ 停止"
    elif avatar_info.get('status') == 'ready':
        btn_text = "▶️ 启动"
    elif avatar_info.get('status') == 'training':
        btn_text = "⏳ 训练中..."
    else:
        btn_text = "❓ 未知"
    
    return status_info, btn_text, ""

def start_or_stop_avatar(avatar_dropdown: str, btn_text: str) -> Tuple[str, str, str]:
    """启动或停止数字人"""
    if not avatar_dropdown:
        return "", "请先选择数字人", "▶️ 启动"
    
    if "启动" in btn_text:
        return start_avatar(avatar_dropdown)
    else:
        return stop_avatar(avatar_dropdown)

def start_avatar(avatar_id: str) -> Tuple[str, str, str]:
    """启动数字人"""
    try:
        response = requests.post(f"{BACKEND_API}/start", json={"avatar_id": avatar_id})
        
        if response.status_code == 200:
            result = response.json()
            
            # WebRTC iframe
            webrtc_html = f'''
            <iframe 
                src="{WEBRTC_URL}" 
                width="100%" 
                height="600" 
                frameborder="0"
                allow="camera; microphone; display-capture"
                style="border-radius: 12px; background: #000;">
            </iframe>
            <div style="text-align: center; margin-top: 10px; color: #666;">
                WebRTC: {WEBRTC_URL} | PID: {result.get('pid', 'N/A')}
            </div>
            '''
            
            manager.refresh_avatars()
            return webrtc_html, f"✅ {avatar_id} 已启动", "⏸️ 停止"
        else:
            error_msg = response.json().get("detail", "启动失败")
            return "", f"❌ {error_msg}", "▶️ 启动"
            
    except Exception as e:
        return "", f"❌ 错误: {str(e)}", "▶️ 启动"

def stop_avatar(avatar_id: str) -> Tuple[str, str, str]:
    """停止数字人"""
    try:
        response = requests.post(f"{BACKEND_API}/stop", json={"avatar_id": avatar_id})
        
        manager.refresh_avatars()
        
        if response.status_code == 200:
            return "", f"✅ {avatar_id} 已停止", "▶️ 启动"
        else:
            return "", f"⚠️ 停止请求已发送", "▶️ 启动"
            
    except Exception as e:
        return "", f"❌ 错误: {str(e)}", "⏸️ 停止"

def refresh_avatar_list() -> gr.Dropdown:
    """刷新数字人列表"""
    avatar_list = manager.refresh_avatars()
    return gr.Dropdown(choices=avatar_list)

def check_backend_health() -> str:
    """检查后端状态"""
    try:
        response = requests.get(f"{BACKEND_API}/health", timeout=2)
        if response.status_code == 200:
            data = response.json()
            return f"""
🟢 后端状态: {data['status']}
LiveTalking路径: {'✅' if data['livetalking_path'] else '❌'}
数字人目录: {'✅' if data['avatars_dir'] else '❌'}
训练结果目录: {'✅' if data['results_dir'] else '❌'}
已有数字人: {data['total_avatars']} 个
运行中: {data['running']} 个
训练中: {data['training']} 个
"""
    except:
        return "🔴 后端未连接"

# 自定义CSS
custom_css = """
.container {
    max-width: 1600px;
    margin: 0 auto;
}
.video-container {
    background: #000;
    border-radius: 12px;
    min-height: 600px;
}
.avatar-card {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 8px;
    padding: 12px;
    color: white;
}
"""

# 创建Gradio界面
with gr.Blocks(title="LiveTalking数字人系统", css=custom_css, theme=gr.themes.Soft()) as app:
    gr.Markdown(
        """
        # 🤖 LiveTalking 数字人系统 V2
        支持MP4视频训练 | WAV音频参考 | 自动扫描已有数字人
        """
    )
    
    with gr.Row():
        # 左侧控制面板
        with gr.Column(scale=1):
            # 系统状态
            with gr.Group():
                gr.Markdown("### 🔌 系统状态")
                backend_status = gr.Textbox(
                    label="",
                    value=check_backend_health(),
                    interactive=False,
                    lines=7
                )
                check_btn = gr.Button("🔄 检查连接", size="sm")
            
            # 数字人选择
            with gr.Group():
                gr.Markdown("### 👤 数字人管理")
                
                action_radio = gr.Radio(
                    ["选择现有数字人", "创建新数字人"],
                    value="选择现有数字人",
                    label="操作选择"
                )
                
                avatar_dropdown = gr.Dropdown(
                    label="已有数字人",
                    choices=manager.refresh_avatars(),
                    interactive=True
                )
                
                with gr.Row():
                    select_btn = gr.Button("选择", variant="primary", size="sm")
                    refresh_btn = gr.Button("刷新", size="sm")
            
            # 创建/训练新数字人
            with gr.Group(visible=False) as create_group:
                gr.Markdown("### ➕ 创建新数字人")
                
                avatar_name_input = gr.Textbox(
                    label="数字人ID (英文)",
                    placeholder="例如: avatarAlice (不需要wav2lip256_前缀)",
                    value=""
                )
                
                video_input = gr.File(
                    label="上传MP4视频 (必须)",
                    file_types=[".mp4"],
                    type="filepath"
                )
                
                audio_input = gr.File(
                    label="上传WAV音频 (必须)",
                    file_types=[".wav"],
                    type="filepath"
                )
                
                ref_text_input = gr.Textbox(
                    label="音频文本内容 (必填)",
                    placeholder="准确输入音频中说的话",
                    value="",
                    lines=2
                )
                
                prompt_input = gr.Textbox(
                    label="系统提示词 (可选)",
                    placeholder="定义数字人的角色...",
                    value="你是一个友好、专业的数字助手。",
                    lines=2
                )
                
                train_btn = gr.Button("🚀 开始训练", variant="primary")
            
            # 状态显示
            status_text = gr.Textbox(
                label="当前状态",
                value="请选择或创建一个数字人",
                interactive=False,
                lines=4
            )
        
        # 中间视频显示
        with gr.Column(scale=2):
            gr.Markdown("### 🎥 数字人视频 (WebRTC)")
            video_output = gr.HTML(
                value='<div style="background: #1a1a1a; height: 600px; display: flex; align-items: center; justify-content: center; color: #666; border-radius: 12px; font-size: 20px;">请选择并启动数字人</div>'
            )
            
            with gr.Row():
                start_stop_btn = gr.Button("▶️ 启动", variant="primary", size="lg")
        
        # 右侧信息面板
        with gr.Column(scale=1):
            gr.Markdown("### 📊 使用说明")
            gr.Markdown(
                """
                **快速开始：**
                1. 选择已有数字人，或
                2. 创建新数字人（需要MP4视频+WAV音频）
                3. 点击"启动"开始使用
                
                **文件要求：**
                - 视频：MP4格式，建议256x256
                - 音频：WAV格式，10-30秒清晰语音
                - 文本：准确输入音频内容
                
                **状态说明：**
                - ✅ 就绪：可以启动
                - ▶️ 运行中：正在使用
                - 🔄 训练中：请等待
                - ❌ 错误：需要重新训练
                
                **注意事项：**
                - 训练需要10-20分钟
                - 每次只能运行一个数字人
                - 切换前请先停止当前数字人
                """
            )
    
    # 事件绑定
    def toggle_create_group(action):
        """切换创建组的显示"""
        return gr.Group(visible=(action == "创建新数字人"))
    
    action_radio.change(
        fn=toggle_create_group,
        inputs=[action_radio],
        outputs=[create_group]
    )
    
    select_btn.click(
        fn=select_avatar,
        inputs=[avatar_dropdown],
        outputs=[status_text, start_stop_btn, video_output]
    )
    
    refresh_btn.click(
        fn=refresh_avatar_list,
        outputs=[avatar_dropdown]
    )
    
    check_btn.click(
        fn=check_backend_health,
        outputs=[backend_status]
    )
    
    train_btn.click(
        fn=create_or_train_avatar,
        inputs=[
            action_radio,
            avatar_name_input,
            video_input,
            audio_input,
            ref_text_input,
            prompt_input
        ],
        outputs=[avatar_dropdown, status_text, video_output]
    )
    
    start_stop_btn.click(
        fn=start_or_stop_avatar,
        inputs=[avatar_dropdown, start_stop_btn],
        outputs=[video_output, status_text, start_stop_btn]
    )
    
    # 定时刷新
    timer = gr.Timer(value=10)
    timer.tick(
        fn=check_backend_health,
        outputs=[backend_status]
    )
    
    # 定时刷新数字人列表
    timer2 = gr.Timer(value=30)
    timer2.tick(
        fn=refresh_avatar_list,
        outputs=[avatar_dropdown]
    )

if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════╗
    ║      🤖 LiveTalking 数字人系统 V2                      ║
    ║                                                      ║
    ║  支持功能:                                            ║
    ║  • MP4视频上传训练                                     ║
    ║  • WAV音频参考                                        ║
    ║  • 自动扫描已有数字人                                  ║
    ║  • 自动移动训练结果                                    ║
    ║                                                      ║
    ║  后端地址: http://localhost:8000                      ║
    ║  前端地址: http://localhost:7860                      ║
    ╚══════════════════════════════════════════════════════╝
    """)
    
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        inbrowser=True
    )
