@echo off
title LiveTalking数字人系统 V2 启动器
color 0A

echo ========================================
echo    LiveTalking 数字人系统 V2
echo    支持MP4视频 + WAV音频
echo ========================================
echo.

REM 检查Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到Python，请先安装Python
    pause
    exit /b 1
)

echo [1/3] 正在安装/更新依赖...
pip install fastapi uvicorn gradio requests psutil -q

echo.
echo [2/3] 启动后端服务 V2...
start "LiveTalking后端V2" cmd /k python livetalking_backend_v2.py

echo.
echo 等待后端启动...
timeout /t 5 /nobreak >nul

echo.
echo [3/3] 启动前端界面 V2...
start "LiveTalking前端V2" cmd /k python frontend_v2.py

echo.
echo ========================================
echo    系统启动完成！
echo.
echo    前端地址: http://localhost:7860
echo    后端地址: http://localhost:8000
echo.
echo    功能特性:
echo    - 支持MP4视频上传
echo    - 支持WAV音频参考
echo    - 自动扫描已有数字人
echo    - 自动管理训练结果
echo.
echo    按任意键退出此窗口（服务继续运行）
echo ========================================
pause >nul
