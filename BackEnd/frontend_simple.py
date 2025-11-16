"""
LiveTalking 前端界面 - 简化稳定版
"""

import gradio as gr
import requests
import time
import threading
from typing import List, Dict, Tuple
import os

# 配置
BACKEND_URL = "http://localhost:8000"

# 全局变量
current_avatar = None
available_avatars = []

def refresh_avatars():
    """刷新数字人列表"""
    global available_avatars
    try:
        response = requests.get(f"{BACKEND_URL}/avatars")
        if response.status_code == 200:
            avatars = response.json()["avatars"]
            available_avatars = avatars
            # 创建选项列表
            choices = []
            for avatar in avatars:
                status = "🟢" if avatar["is_running"] else "⚪"
                audio = "🔊" if avatar["has_audio"] else "🔇"
                choices.append(f"{status} {audio} {avatar['name']}")
            return choices
    except Exception as e:
        print(f"刷新失败: {e}")
    return []

def get_avatar_by_name(name):
    """根据显示名称获取数字人信息"""
    # 去除状态图标，获取真实名称
    clean_name = name.split()[-1] if name else ""
    for avatar in available_avatars:
        if avatar["name"] == clean_name:
            return avatar
    return None

def start_existing_avatar(avatar_select, ref_text):
    """启动现有数字人"""
    if not avatar_select:
        return "请选择一个数字人", ""
    
    avatar = get_avatar_by_name(avatar_select)
    if not avatar:
        return "未找到数字人", ""
    
    # 检查音频文件
    if not avatar["has_audio"]:
        return f"❌ {avatar['name']} 没有音频文件，无法启动", ""
    
    # 默认音频路径
    ref_file = f"wav/{avatar['id']}.wav"
    
    # 如果没有提供文本，使用默认
    if not ref_text:
        ref_text = "Hello, I am a digital avatar."
    
    try:
        response = requests.post(
            f"{BACKEND_URL}/start",
            json={
                "avatar_id": avatar["id"],
                "ref_file": ref_file,
                "ref_text": ref_text
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            global current_avatar
            current_avatar = avatar["id"]
            
            # WebRTC iframe
            video_html = f'''
            <iframe 
                src="http://localhost:8010" 
                width="100%" 
                height="600" 
                frameborder="0"
                allow="camera; microphone"
                style="border-radius: 10px; background: #000;">
            </iframe>
            '''
            return f"✅ 启动成功 (PID: {data['pid']})", video_html
        else:
            error = response.json().get("detail", "未知错误")
            return f"❌ 启动失败: {error}", ""
            
    except Exception as e:
        return f"❌ 错误: {e}", ""

def stop_current_avatar():
    """停止当前数字人"""
    global current_avatar
    if not current_avatar:
        return "没有运行中的数字人"
    
    try:
        response = requests.post(f"{BACKEND_URL}/stop/{current_avatar}")
        current_avatar = None
        return "✅ 已停止"
    except Exception as e:
        return f"❌ 停止失败: {e}"

def train_new_avatar(avatar_name, video_file, audio_file, ref_text):
    """训练新数字人"""
    # 验证输入
    if not all([avatar_name, video_file, audio_file, ref_text]):
        return "❌ 请填写所有字段"
    
    if not video_file.endswith('.mp4'):
        return "❌ 视频必须是MP4格式"
    
    if not audio_file.endswith('.wav'):
        return "❌ 音频必须是WAV格式"
    
    try:
        # 上传视频
        with open(video_file, "rb") as f:
            response = requests.post(
                f"{BACKEND_URL}/upload/video",
                files={"file": ("video.mp4", f, "video/mp4")}
            )
            if response.status_code != 200:
                return f"❌ 视频上传失败"
            video_path = response.json()["path"]
        
        # 上传音频
        with open(audio_file, "rb") as f:
            response = requests.post(
                f"{BACKEND_URL}/upload/audio",
                files={"file": ("audio.wav", f, "audio/wav")}
            )
            if response.status_code != 200:
                return f"❌ 音频上传失败"
            audio_path = response.json()["path"]
        
        # 开始训练
        response = requests.post(
            f"{BACKEND_URL}/train",
            json={
                "avatar_id": avatar_name,
                "video_path": video_path,
                "audio_path": audio_path,
                "ref_text": ref_text
            }
        )
        
        if response.status_code == 200:
            avatar_id = response.json()["avatar_id"]
            
            # 启动监控线程
            threading.Thread(
                target=monitor_training,
                args=(avatar_id,),
                daemon=True
            ).start()
            
            return f"✅ 开始训练 {avatar_id}，预计需要10-20分钟..."
        else:
            return f"❌ 训练请求失败"
            
    except Exception as e:
        return f"❌ 错误: {e}"

def monitor_training(avatar_id):
    """监控训练状态"""
    while True:
        try:
            response = requests.get(f"{BACKEND_URL}/training/{avatar_id}")
            if response.status_code == 200:
                status = response.json()["status"]
                if status == "completed":
                    print(f"✅ {avatar_id} 训练完成！")
                    break
                elif status == "error":
                    print(f"❌ {avatar_id} 训练失败！")
                    break
        except:
            pass
        time.sleep(10)

def check_health():
    """检查后端状态"""
    try:
        response = requests.get(f"{BACKEND_URL}/health")
        if response.status_code == 200:
            data = response.json()
            return f"""
系统状态: ✅
数字人总数: {data['avatars_count']}
运行中: {data['running_count']}
训练中: {data['training_count']}
"""
    except:
        return "系统状态: ❌ 后端未连接"

# 创建界面
with gr.Blocks(title="LiveTalking数字人系统", theme=gr.themes.Soft()) as app:
    gr.Markdown("# 🤖 LiveTalking 数字人系统")
    
    with gr.Tabs():
        # Tab 1: 使用现有数字人
        with gr.Tab("使用现有数字人"):
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### 选择数字人")
                    
                    # 数字人列表
                    avatar_dropdown = gr.Dropdown(
                        label="可用数字人",
                        choices=refresh_avatars(),
                        interactive=True
                    )
                    
                    # 刷新按钮
                    refresh_btn = gr.Button("🔄 刷新列表", size="sm")
                    
                    # 音频文本（可选）
                    ref_text_input = gr.Textbox(
                        label="参考文本（可选）",
                        placeholder="默认: Hello, I am a digital avatar.",
                        value=""
                    )
                    
                    # 控制按钮
                    with gr.Row():
                        start_btn = gr.Button("▶️ 启动", variant="primary")
                        stop_btn = gr.Button("⏹️ 停止", variant="stop")
                    
                    # 状态显示
                    status_text = gr.Textbox(
                        label="状态",
                        value="请选择一个数字人",
                        interactive=False
                    )
                
                with gr.Column(scale=2):
                    gr.Markdown("### 视频输出")
                    video_output = gr.HTML(
                        value='<div style="background:#000; height:600px; display:flex; align-items:center; justify-content:center; color:#666; border-radius:10px;">等待启动...</div>'
                    )
        
        # Tab 2: 创建新数字人
        with gr.Tab("创建新数字人"):
            with gr.Row():
                with gr.Column():
                    gr.Markdown("### 训练新数字人")
                    
                    # 输入字段
                    name_input = gr.Textbox(
                        label="数字人名称（英文）",
                        placeholder="例如: avatarAlice (不需要wav2lip256_前缀)"
                    )
                    
                    video_input = gr.File(
                        label="上传MP4视频",
                        file_types=[".mp4"],
                        type="filepath"
                    )
                    
                    audio_input = gr.File(
                        label="上传WAV音频",
                        file_types=[".wav"],
                        type="filepath"
                    )
                    
                    text_input = gr.Textbox(
                        label="音频文本内容（必填）",
                        placeholder="准确输入音频中说的话",
                        lines=2
                    )
                    
                    train_btn = gr.Button("🚀 开始训练", variant="primary")
                    
                    # 训练状态
                    train_status = gr.Textbox(
                        label="训练状态",
                        value="填写信息后点击开始训练",
                        interactive=False
                    )
                
                with gr.Column():
                    gr.Markdown("""
                    ### 📝 训练说明
                    
                    1. **视频要求**
                       - 格式：MP4
                       - 建议分辨率：256x256或更高
                       - 内容：清晰的人脸正面视频
                    
                    2. **音频要求**
                       - 格式：WAV
                       - 时长：10-30秒
                       - 质量：清晰无噪音
                    
                    3. **训练时间**
                       - 通常需要10-20分钟
                       - 训练完成后自动添加到可用列表
                    
                    4. **注意事项**
                       - Avatar ID只能使用英文和数字
                       - 音频文本必须准确
                       - 训练期间请勿关闭程序
                    """)
        
        # Tab 3: 系统状态
        with gr.Tab("系统状态"):
            gr.Markdown("### 系统信息")
            
            health_text = gr.Textbox(
                label="后端状态",
                value=check_health(),
                interactive=False,
                lines=5
            )
            
            check_health_btn = gr.Button("🔄 刷新状态")
            
            gr.Markdown("""
            ### 图例说明
            - 🟢 运行中
            - ⚪ 就绪
            - 🔊 有音频文件
            - 🔇 无音频文件
            
            ### 目录结构
            ```
            LiveTalking-main/
            ├── data/avatars/        # 数字人文件
            ├── wav/                 # 音频文件
            └── wav2lip/results/     # 训练输出
            ```
            """)
    
    # 事件绑定
    refresh_btn.click(
        fn=lambda: gr.Dropdown(choices=refresh_avatars()),
        outputs=[avatar_dropdown]
    )
    
    start_btn.click(
        fn=start_existing_avatar,
        inputs=[avatar_dropdown, ref_text_input],
        outputs=[status_text, video_output]
    )
    
    stop_btn.click(
        fn=stop_current_avatar,
        outputs=[status_text]
    )
    
    train_btn.click(
        fn=train_new_avatar,
        inputs=[name_input, video_input, audio_input, text_input],
        outputs=[train_status]
    )
    
    check_health_btn.click(
        fn=check_health,
        outputs=[health_text]
    )
    
    # 定期刷新
    def auto_refresh():
        return gr.Dropdown(choices=refresh_avatars())
    
    # 每30秒自动刷新列表
    timer = gr.Timer(value=30)
    timer.tick(fn=auto_refresh, outputs=[avatar_dropdown])

if __name__ == "__main__":
    print("""
    ╔════════════════════════════════════════╗
    ║   LiveTalking 数字人系统 - 简化版       ║
    ╠════════════════════════════════════════╣
    ║   功能：                                ║
    ║   • 使用现有数字人（直接运行）           ║
    ║   • 创建新数字人（MP4+WAV训练）         ║
    ║   • 系统状态监控                        ║
    ╠════════════════════════════════════════╣
    ║   后端: http://localhost:8000           ║
    ║   前端: http://localhost:7860           ║
    ╚════════════════════════════════════════╝
    """)
    
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        inbrowser=True
    )
