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
WEBRTC_URL = "http://localhost:8010"  # LiveTalking WebRTC地址

class DigitalHumanSession:
    """数字人会话管理类"""
    def __init__(self, session_id: str, name: str):
        self.session_id = session_id
        self.name = name
        self.avatar_id = ""
        self.ref_text = ""
        self.prompt = ""
        self.status = "idle"
        self.chat_history = []
        self.image_path = None
        self.audio_path = None
        self.video_path = None
        self.creation_time = datetime.now()
        self.is_running = False
        self.pid = None
        
class DigitalHumanManager:
    """数字人管理器"""
    def __init__(self):
        self.sessions: Dict[str, DigitalHumanSession] = {}
        self.current_session_id = None
        
    def create_session(self, session_id: str, name: str, avatar_id: str, ref_text: str, prompt: str) -> DigitalHumanSession:
        """创建新的数字人会话"""
        session = DigitalHumanSession(session_id, name)
        session.avatar_id = avatar_id
        session.ref_text = ref_text
        session.prompt = prompt
        session.status = "training"
        self.sessions[session_id] = session
        return session
    
    def get_session_list(self) -> List[Tuple[str, str]]:
        """获取会话列表"""
        result = []
        for sid, s in self.sessions.items():
            status_emoji = {
                "idle": "⚫",
                "training": "🔄",
                "ready": "✅",
                "running": "▶️",
                "error": "❌"
            }.get(s.status, "❓")
            result.append((sid, f"{status_emoji} {s.name} ({s.avatar_id})"))
        return result
    
    def switch_session(self, session_id: str) -> bool:
        """切换会话"""
        if self.current_session_id and self.sessions[self.current_session_id].is_running:
            self.stop_current_session()
        self.current_session_id = session_id
        return True
    
    def stop_current_session(self):
        """停止当前会话的视频输出"""
        if self.current_session_id:
            session = self.sessions[self.current_session_id]
            if session.is_running:
                try:
                    requests.post(f"{BACKEND_API}/stop", json={"session_id": self.current_session_id})
                    session.is_running = False
                except:
                    pass

# 创建全局管理器实例
manager = DigitalHumanManager()

# ========== 主要功能函数 ==========
def create_new_session(name: str, avatar_id: str, image_file, audio_file, ref_text: str, prompt: str) -> Tuple[gr.Dropdown, str, str]:
    """创建新的数字人会话"""
    
    # 验证必填字段
    if not all([name, avatar_id, image_file, audio_file, ref_text]):
        return gr.Dropdown(choices=manager.get_session_list()), "❌ 请填写所有必填字段", ""
    
    try:
        # 1. 上传图片并生成视频
        with open(image_file, "rb") as f:
            response = requests.post(
                f"{BACKEND_API}/upload/image",
                files={"file": (os.path.basename(image_file), f, "image/jpeg")}
            )
        
        if response.status_code != 200:
            return gr.Dropdown(choices=manager.get_session_list()), "❌ 图片上传失败", ""
        
        image_data = response.json()
        video_path = image_data["video_path"]
        image_path = image_data["image_path"]
        
        # 2. 上传音频
        with open(audio_file, "rb") as f:
            response = requests.post(
                f"{BACKEND_API}/upload/audio",
                files={"file": (os.path.basename(audio_file), f, "audio/wav")}
            )
        
        if response.status_code != 200:
            return gr.Dropdown(choices=manager.get_session_list()), "❌ 音频上传失败", ""
        
        audio_data = response.json()
        audio_path = audio_data["audio_path"]
        
        # 3. 发送训练请求
        train_data = {
            "session_id": avatar_id,  # 使用avatar_id作为session_id
            "avatar_id": f"wav2lip256_{avatar_id}",  # 添加前缀
            "video_path": video_path,
            "audio_path": audio_path,
            "ref_text": ref_text,
            "prompt": prompt or "你是一个友好的数字助手"
        }
        
        response = requests.post(f"{BACKEND_API}/train", json=train_data)
        
        if response.status_code != 200:
            return gr.Dropdown(choices=manager.get_session_list()), f"❌ 训练请求失败: {response.text}", ""
        
        result = response.json()
        session_id = result["session_id"]
        
        # 4. 创建本地会话
        session = manager.create_session(session_id, name, avatar_id, ref_text, prompt)
        session.image_path = image_path
        session.audio_path = audio_path
        session.video_path = video_path
        
        # 5. 启动状态监控线程
        threading.Thread(target=monitor_training, args=(session_id,), daemon=True).start()
        
        return (
            gr.Dropdown(choices=manager.get_session_list(), value=session_id),
            f"✅ 创建成功！正在训练数字人 '{avatar_id}'，预计需要5-10分钟...",
            ""
        )
        
    except Exception as e:
        return gr.Dropdown(choices=manager.get_session_list()), f"❌ 创建失败: {str(e)}", ""

def monitor_training(session_id: str):
    """监控训练状态"""
    session = manager.sessions[session_id]
    
    while session.status == "training":
        try:
            response = requests.get(f"{BACKEND_API}/session/{session_id}")
            if response.status_code == 200:
                data = response.json()
                session.status = data["status"]
                
                if session.status == "ready":
                    print(f"✅ 训练完成: {session_id}")
                elif session.status == "error":
                    print(f"❌ 训练失败: {session_id}")
                    if "error" in data:
                        print(f"错误信息: {data['error']}")
        except:
            pass
        
        time.sleep(5)  # 每5秒检查一次

def switch_session(session_id: str) -> Tuple[list, str, str, str, str, str]:
    """切换到指定会话"""
    if not session_id or session_id not in manager.sessions:
        return [], "", "", "▶️ 开始运行", "请选择有效的会话", ""
    
    manager.switch_session(session_id)
    session = manager.sessions[session_id]
    
    # 获取最新状态
    try:
        response = requests.get(f"{BACKEND_API}/session/{session_id}")
        if response.status_code == 200:
            data = response.json()
            session.status = data["status"]
            session.is_running = data.get("is_running", False)
            session.pid = data.get("pid")
    except:
        pass
    
    # 构建状态信息
    status_info = f"""
当前会话: {session.name}
Avatar ID: {session.avatar_id}
状态: {session.status}
参考文本: {session.ref_text[:50]}...
"""
    if session.pid:
        status_info += f"进程PID: {session.pid}"
    
    # 根据状态设置按钮
    if session.is_running:
        btn_text = "⏸️ 停止"
    elif session.status == "ready":
        btn_text = "▶️ 开始运行"
    elif session.status == "training":
        btn_text = "⏳ 训练中..."
    else:
        btn_text = "❌ 错误"
    
    return (
        session.chat_history,
        session.prompt,
        session.ref_text,
        btn_text,
        status_info,
        ""
    )

def start_digital_human(session_id: str) -> Tuple[str, str, str]:
    """启动数字人视频输出"""
    if not session_id or session_id not in manager.sessions:
        return "", "请先选择会话", "▶️ 开始运行"
    
    session = manager.sessions[session_id]
    
    try:
        # 发送启动请求
        response = requests.post(f"{BACKEND_API}/start", json={"session_id": session_id})
        
        if response.status_code == 200:
            result = response.json()
            session.is_running = True
            session.status = "running"
            session.pid = result.get("pid")
            
            # 生成WebRTC iframe
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
                WebRTC连接: {WEBRTC_URL} | PID: {session.pid}
            </div>
            '''
            
            return webrtc_html, f"✅ 数字人已启动 (PID: {session.pid})", "⏸️ 停止"
        else:
            error_msg = response.json().get("detail", "未知错误")
            return "", f"❌ 启动失败: {error_msg}", "▶️ 开始运行"
            
    except Exception as e:
        return "", f"❌ 启动失败: {str(e)}", "▶️ 开始运行"

def stop_digital_human(session_id: str) -> Tuple[str, str]:
    """停止数字人视频输出"""
    if session_id and session_id in manager.sessions:
        try:
            response = requests.post(f"{BACKEND_API}/stop", json={"session_id": session_id})
            
            session = manager.sessions[session_id]
            session.is_running = False
            session.status = "ready"
            session.pid = None
            
            if response.status_code == 200:
                return "✅ 已停止", "▶️ 开始运行"
            else:
                return "⚠️ 停止请求已发送", "▶️ 开始运行"
                
        except Exception as e:
            return f"❌ 停止失败: {str(e)}", "▶️ 开始运行"
    
    return "未找到会话", "▶️ 开始运行"

def send_message(message: str, chat_history: list, session_id: str) -> Tuple[list, str, str]:
    """发送消息到数字人"""
    if not session_id or session_id not in manager.sessions:
        return chat_history, "", "❌ 请先选择会话"
    
    session = manager.sessions[session_id]
    
    if not session.is_running:
        return chat_history, "", "⚠️ 数字人未运行，请先启动"
    
    if not message.strip():
        return chat_history, "", ""
    
    # 添加到聊天历史
    chat_history.append([message, "（数字人回复将通过视频展示）"])
    session.chat_history = chat_history
    
    # 发送到后端（虽然实际对话通过WebRTC）
    try:
        requests.post(f"{BACKEND_API}/chat", json={
            "session_id": session_id,
            "message": message
        })
        status = "✅ 消息已发送，请查看视频回应"
    except Exception as e:
        status = f"⚠️ 发送失败: {str(e)}"
    
    return chat_history, "", status

def refresh_sessions() -> Tuple[gr.Dropdown, str]:
    """刷新会话列表和状态"""
    try:
        response = requests.get(f"{BACKEND_API}/sessions")
        if response.status_code == 200:
            data = response.json()
            
            # 更新本地会话状态
            for session_data in data["sessions"]:
                sid = session_data["session_id"]
                if sid not in manager.sessions:
                    # 创建新会话对象
                    session = DigitalHumanSession(sid, sid)
                    session.avatar_id = session_data.get("avatar_id", "")
                    session.ref_text = session_data.get("ref_text", "")
                    session.prompt = session_data.get("prompt", "")
                    manager.sessions[sid] = session
                
                # 更新状态
                manager.sessions[sid].status = session_data["status"]
            
            return gr.Dropdown(choices=manager.get_session_list()), f"已刷新 ({len(manager.sessions)} 个会话)"
    except Exception as e:
        return gr.Dropdown(choices=manager.get_session_list()), f"刷新失败: {str(e)}"
    
    return gr.Dropdown(choices=manager.get_session_list()), ""

def check_backend_health() -> str:
    """检查后端健康状态"""
    try:
        response = requests.get(f"{BACKEND_API}/health", timeout=2)
        if response.status_code == 200:
            data = response.json()
            return f"""
🟢 后端状态: {data['status']}
LiveTalking: {'✅' if data['livetalking'] else '❌'}
会话总数: {data['sessions']}
运行中: {data['running']}
训练中: {data['training']}
"""
        else:
            return "🔴 后端响应异常"
    except:
        return "🔴 后端未连接"

# 自定义CSS样式
custom_css = """
.container {
    max-width: 1600px;
    margin: 0 auto;
}
.video-container {
    background: #000;
    border-radius: 12px;
    overflow: hidden;
    min-height: 600px;
}
.status-card {
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
        # 🤖 LiveTalking 数字人系统
        基于 LiveTalking + CosyVoice 的实时数字人交互平台
        """
    )
    
    with gr.Row():
        # 左侧控制面板
        with gr.Column(scale=1):
            # 后端状态
            with gr.Group():
                gr.Markdown("### 🔌 系统状态")
                backend_status = gr.Textbox(
                    label="",
                    value=check_backend_health(),
                    interactive=False,
                    lines=5
                )
                check_btn = gr.Button("🔄 检查连接", size="sm")
            
            # 会话管理
            with gr.Group():
                gr.Markdown("### 📁 会话管理")
                session_dropdown = gr.Dropdown(
                    label="选择会话",
                    choices=manager.get_session_list(),
                    interactive=True
                )
                
                with gr.Row():
                    switch_btn = gr.Button("切换", variant="primary", size="sm")
                    refresh_btn = gr.Button("刷新", size="sm")
                    delete_btn = gr.Button("删除", variant="stop", size="sm")
            
            # 创建新数字人
            with gr.Accordion("➕ 创建新数字人", open=True):
                name_input = gr.Textbox(
                    label="数字人名称",
                    placeholder="例如：客服小美",
                    value="测试数字人"
                )
                
                avatar_id_input = gr.Textbox(
                    label="Avatar ID (必填，英文)",
                    placeholder="例如：avatarMan, avatarWoman",
                    value="avatarTest",
                    info="⚠️ 唯一标识符，只能使用英文字母和数字"
                )
                
                image_input = gr.File(
                    label="上传形象图片",
                    file_types=["image"],
                    type="filepath"
                )
                
                audio_input = gr.File(
                    label="上传参考音频 (10-30秒)",
                    file_types=["audio"],
                    type="filepath"
                )
                
                ref_text_input = gr.Textbox(
                    label="音频文本内容 (必填)",
                    placeholder="输入音频中说的话，例如：What can I say? Manba out.",
                    value="你好，我是数字人助手，很高兴为您服务。",
                    lines=2,
                    info="⚠️ 必须准确输入音频中的文字内容"
                )
                
                prompt_input = gr.Textbox(
                    label="系统提示词",
                    placeholder="定义数字人的角色和行为...",
                    value="你是一个友好、专业的数字助手。",
                    lines=3
                )
                
                create_btn = gr.Button("🚀 开始创建", variant="primary")
            
            # 状态显示
            status_text = gr.Textbox(
                label="当前状态",
                value="请创建或选择一个数字人",
                interactive=False,
                lines=5
            )
        
        # 中间视频显示
        with gr.Column(scale=2):
            gr.Markdown("### 🎥 数字人视频 (WebRTC)")
            video_output = gr.HTML(
                value='<div style="background: #1a1a1a; height: 600px; display: flex; align-items: center; justify-content: center; color: #666; border-radius: 12px;">请启动数字人</div>',
                elem_classes="video-container"
            )
            
            with gr.Row():
                start_stop_btn = gr.Button("▶️ 开始运行", variant="primary", size="lg")
                
        # 右侧聊天区域
        with gr.Column(scale=2):
            gr.Markdown("### 💬 对话交互")
            chatbot = gr.Chatbot(
                label="聊天记录",
                height=500,
                bubble_full_width=False
            )
            
            with gr.Row():
                msg_input = gr.Textbox(
                    label="",
                    placeholder="输入消息...",
                    scale=4
                )
                send_btn = gr.Button("发送", variant="primary", scale=1)
            
            chat_status = gr.Textbox(
                label="",
                value="",
                interactive=False
            )
    
    # 显示当前会话的参考文本
    ref_text_display = gr.Textbox(visible=False)
    prompt_display = gr.Textbox(visible=False)
    
    # 事件绑定
    create_btn.click(
        fn=create_new_session,
        inputs=[name_input, avatar_id_input, image_input, audio_input, ref_text_input, prompt_input],
        outputs=[session_dropdown, status_text, video_output]
    )
    
    switch_btn.click(
        fn=switch_session,
        inputs=[session_dropdown],
        outputs=[chatbot, prompt_display, ref_text_display, start_stop_btn, status_text, video_output]
    )
    
    refresh_btn.click(
        fn=refresh_sessions,
        outputs=[session_dropdown, status_text]
    )
    
    check_btn.click(
        fn=check_backend_health,
        outputs=[backend_status]
    )
    
    # 处理开始/停止
    def handle_start_stop(session_id, btn_text):
        if "开始" in btn_text:
            html, status, new_btn = start_digital_human(session_id)
            return html, status, new_btn
        else:
            status, new_btn = stop_digital_human(session_id)
            return "", status, new_btn
    
    start_stop_btn.click(
        fn=handle_start_stop,
        inputs=[session_dropdown, start_stop_btn],
        outputs=[video_output, status_text, start_stop_btn]
    )
    
    # 删除会话
    def delete_session(session_id):
        if session_id:
            try:
                response = requests.delete(f"{BACKEND_API}/session/{session_id}")
                if session_id in manager.sessions:
                    del manager.sessions[session_id]
                return gr.Dropdown(choices=manager.get_session_list()), "✅ 已删除"
            except:
                return gr.Dropdown(choices=manager.get_session_list()), "❌ 删除失败"
        return gr.Dropdown(choices=manager.get_session_list()), ""
    
    delete_btn.click(
        fn=delete_session,
        inputs=[session_dropdown],
        outputs=[session_dropdown, status_text]
    )
    
    # 发送消息
    send_btn.click(
        fn=send_message,
        inputs=[msg_input, chatbot, session_dropdown],
        outputs=[chatbot, msg_input, chat_status]
    )
    
    msg_input.submit(
        fn=send_message,
        inputs=[msg_input, chatbot, session_dropdown],
        outputs=[chatbot, msg_input, chat_status]
    )
    
    # 定时刷新状态
    timer = gr.Timer(value=5)
    timer.tick(
        fn=check_backend_health,
        outputs=[backend_status]
    )

if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════╗
    ║      🤖 LiveTalking 数字人系统 - 前端                  ║
    ║                                                      ║
    ║  后端地址: http://localhost:8000                      ║
    ║  前端地址: http://localhost:7860                      ║
    ║  WebRTC: http://localhost:8010                        ║
    ║                                                      ║
    ║  请确保后端已启动！                                    ║
    ╚══════════════════════════════════════════════════════╝
    """)
    
    # 启动应用
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        inbrowser=True
    )
