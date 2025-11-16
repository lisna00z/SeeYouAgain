# 📘 LiveTalking数字人系统 - 完整使用指南

## 🎯 系统概述

这是一个基于LiveTalking和CosyVoice的完整数字人系统，包含：
- **后端API**：管理数字人的训练和运行
- **前端界面**：类似ChatGPT的交互界面
- **多进程管理**：支持同时运行多个数字人

## 📋 前置要求

### 1. 系统要求
- Windows 10/11
- Python 3.8+
- 至少8GB显存（推荐16GB）
- ffmpeg（用于视频处理）

### 2. LiveTalking配置
确保LiveTalking已正确安装在：
```
D:\Projects\See You Again\src\LiveTalking\LiveTalking-main
```

如果路径不同，请修改 `livetalking_backend.py` 第17行：
```python
LIVETALKING_PATH = r"你的LiveTalking路径"
```

### 3. CosyVoice配置
确保CosyVoice服务运行在：
```
http://127.0.0.1:50000
```

## 🚀 快速启动

### 方法1：使用批处理文件（推荐）
```bash
# 双击运行
start_windows.bat
```

### 方法2：手动启动
```bash
# 1. 安装依赖
pip install -r requirements_backend.txt

# 2. 启动后端（新开一个终端）
python livetalking_backend.py

# 3. 启动前端（再开一个终端）
python frontend_with_backend.py
```

## 📝 使用流程

### 1. 创建数字人

填写以下信息：
- **数字人名称**：显示名称（如"客服小美"）
- **Avatar ID**：唯一标识符（英文，如"avatarMary"）
- **形象图片**：上传人物图片（建议正面照）
- **参考音频**：10-30秒的音频样本
- **音频文本**：准确输入音频中的内容
- **系统提示词**：定义数字人的角色

点击"🚀 开始创建"，等待5-10分钟完成训练。

### 2. 启动数字人

1. 从下拉菜单选择已训练的数字人
2. 点击"切换"按钮
3. 点击"▶️ 开始运行"
4. 等待WebRTC视频加载

### 3. 对话交互

- 在右侧输入框输入消息
- 数字人会通过视频实时回应
- 支持语音和口型同步

## 🔧 重要参数说明

### Avatar ID命名规则
- 只能使用英文字母和数字
- 不要使用中文或特殊字符
- 建议格式：`avatarName`

### 音频文本（REF_TEXT）
- 必须准确输入音频中说的话
- 用于语音克隆的参考
- 影响生成的语音质量

### 文件要求
- **图片**：JPG/PNG，建议256x256或更高
- **音频**：WAV/MP3，10-30秒，清晰无噪音
- **视频**：系统会自动从图片生成

## 🛠️ 常见问题

### Q1: 提示"LiveTalking路径不存在"
**解决方案**：
1. 确认LiveTalking安装路径
2. 修改 `livetalking_backend.py` 中的 `LIVETALKING_PATH`

### Q2: 训练失败
**可能原因**：
- 图片质量不佳（需要清晰的人脸）
- 音频有噪音或时长不合适
- 显存不足

**解决方案**：
- 使用高质量的正面人脸照片
- 录制清晰的音频（10-30秒）
- 关闭其他GPU程序释放显存

### Q3: 视频不显示
**解决方案**：
1. 检查LiveTalking是否正常启动（查看控制台）
2. 确认WebRTC端口（8010）未被占用
3. 尝试刷新浏览器

### Q4: 多个数字人冲突
**解决方案**：
- 使用不同的Avatar ID
- 确保先停止当前数字人再启动新的

### Q5: 进程无法关闭
**解决方案**：
```bash
# 手动终止进程
taskkill /F /PID [进程ID]

# 或使用任务管理器
# 查找python.exe进程并结束
```

## 📂 文件结构

```
项目目录/
├── livetalking_backend.py    # 后端API服务
├── frontend_with_backend.py  # 前端界面
├── requirements_backend.txt  # 依赖列表
├── start_windows.bat         # 启动脚本
├── uploads/                  # 上传文件目录
├── models/                   # 训练模型目录
└── logs/                     # 日志文件目录
```

## 🔍 系统架构

```
前端(Gradio) <--HTTP--> 后端(FastAPI) <--进程--> LiveTalking
                                      <--HTTP--> CosyVoice
```

### 后端API端点

- `POST /train` - 训练数字人
- `POST /start` - 启动数字人
- `POST /stop` - 停止数字人
- `POST /chat` - 发送消息
- `GET /sessions` - 获取所有会话
- `GET /health` - 健康检查

## 💡 高级配置

### 修改端口
```python
# 后端端口（livetalking_backend.py）
uvicorn.run(app, port=8000)  # 改为其他端口

# 前端端口（frontend_with_backend.py）
app.launch(server_port=7860)  # 改为其他端口

# 同时更新前端的后端地址
BACKEND_API = "http://localhost:8000"  # 改为对应端口
```

### 修改TTS服务器
```python
# livetalking_backend.py
TTS_SERVER = "http://127.0.0.1:50000"  # 改为实际地址
```

### 调试模式
查看详细日志：
```bash
# 日志文件位置
logs/backend.log        # 后端日志
logs/train_*.log       # 训练日志
logs/run_*.log         # 运行日志
```

## ⚠️ 注意事项

1. **资源占用**：每个数字人会占用约2-4GB显存
2. **并发限制**：建议同时运行不超过3个数字人
3. **网络要求**：WebRTC需要稳定的网络连接
4. **安全性**：生产环境请配置适当的访问控制

## 📞 技术支持

遇到问题时，请提供：
1. 错误截图
2. `logs/backend.log` 文件
3. 系统配置信息（Python版本、显卡型号等）

## 🎉 成功标志

系统正常运行时，你应该看到：
- ✅ 后端显示"LiveTalking检查通过"
- ✅ 前端显示"🟢 后端状态: healthy"
- ✅ 能够成功创建和训练数字人
- ✅ WebRTC视频正常显示
- ✅ 语音和口型同步正常

---

祝你使用愉快！如有问题，请查看日志文件获取详细信息。
