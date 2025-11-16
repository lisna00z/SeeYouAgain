@echo off
title LiveTalking 简化版启动器
color 0A

echo ========================================
echo    LiveTalking 数字人系统 - 简化稳定版
echo ========================================
echo.

REM 检查Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到Python
    pause
    exit /b 1
)

echo [1/4] 安装依赖...
pip install fastapi uvicorn gradio requests psutil -q

echo.
echo [2/4] 创建必要目录...
mkdir uploads 2>nul
mkdir logs 2>nul

echo.
echo [3/4] 启动后端...
start "后端 - LiveTalking" cmd /k python backend_simple.py

echo.
echo 等待后端启动...
timeout /t 5 /nobreak >nul

echo.
echo [4/4] 启动前端...
start "前端 - LiveTalking" cmd /k python frontend_simple.py

echo.
echo ========================================
echo.
echo    ✅ 启动完成！
echo.
echo    前端: http://localhost:7860
echo    后端: http://localhost:8000
echo.
echo    使用说明:
echo    Tab 1 - 使用现有数字人（直接运行）
echo    Tab 2 - 创建新数字人（训练）
echo    Tab 3 - 查看系统状态
echo.
echo    按任意键关闭此窗口（服务继续运行）
echo ========================================
pause >nul
