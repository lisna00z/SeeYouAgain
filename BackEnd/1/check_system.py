"""
LiveTalking系统配置检查工具
"""

import os
import sys
import subprocess
from pathlib import Path
import importlib.util

def check_python():
    """检查Python版本"""
    print("🔍 检查Python版本...")
    version = sys.version_info
    if version >= (3, 8):
        print(f"✅ Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"❌ Python版本过低: {version.major}.{version.minor}")
        print("   需要Python 3.8+")
        return False

def check_packages():
    """检查必要的包"""
    print("\n🔍 检查依赖包...")
    
    required = {
        "fastapi": "FastAPI",
        "uvicorn": "Uvicorn",
        "gradio": "Gradio",
        "requests": "Requests",
        "psutil": "PSUtil"
    }
    
    missing = []
    for package, name in required.items():
        spec = importlib.util.find_spec(package)
        if spec is None:
            print(f"❌ {name} 未安装")
            missing.append(package)
        else:
            print(f"✅ {name} 已安装")
    
    if missing:
        print(f"\n缺少的包: {', '.join(missing)}")
        print("运行以下命令安装:")
        print(f"pip install {' '.join(missing)}")
        return False
    
    return True

def check_livetalking():
    """检查LiveTalking"""
    print("\n🔍 检查LiveTalking...")
    
    # 默认路径
    default_path = r"D:\Projects\See You Again\src\LiveTalking\LiveTalking-main"
    
    if os.path.exists(default_path):
        print(f"✅ LiveTalking找到: {default_path}")
        
        # 检查关键文件
        app_py = os.path.join(default_path, "app.py")
        wav2lip_dir = os.path.join(default_path, "wav2lip")
        
        if os.path.exists(app_py):
            print("✅ app.py 存在")
        else:
            print("❌ app.py 不存在")
            
        if os.path.exists(wav2lip_dir):
            print("✅ wav2lip目录 存在")
            genavatar = os.path.join(wav2lip_dir, "genavatar.py")
            if os.path.exists(genavatar):
                print("✅ genavatar.py 存在")
            else:
                print("❌ genavatar.py 不存在")
        else:
            print("❌ wav2lip目录 不存在")
            
        return True
    else:
        print(f"❌ LiveTalking未找到: {default_path}")
        print("\n请修改 livetalking_backend.py 中的 LIVETALKING_PATH")
        return False

def check_ffmpeg():
    """检查FFmpeg"""
    print("\n🔍 检查FFmpeg...")
    
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            version = result.stdout.split('\n')[0]
            print(f"✅ FFmpeg已安装: {version}")
            return True
    except FileNotFoundError:
        pass
    
    print("⚠️  FFmpeg未安装（用于图片转视频）")
    print("   下载地址: https://ffmpeg.org/download.html")
    print("   安装后需要添加到系统PATH")
    return False

def check_ports():
    """检查端口占用"""
    print("\n🔍 检查端口...")
    
    try:
        import socket
        
        ports = {
            8000: "后端API",
            7860: "前端界面",
            8010: "WebRTC",
            50000: "CosyVoice"
        }
        
        for port, service in ports.items():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('localhost', port))
            sock.close()
            
            if result == 0:
                print(f"⚠️  端口 {port} ({service}) 已被占用")
            else:
                print(f"✅ 端口 {port} ({service}) 可用")
                
    except Exception as e:
        print(f"❌ 端口检查失败: {e}")
    
    return True

def check_gpu():
    """检查GPU（可选）"""
    print("\n🔍 检查GPU（可选）...")
    
    try:
        import torch
        if torch.cuda.is_available():
            print(f"✅ CUDA可用: {torch.cuda.get_device_name(0)}")
            print(f"   显存: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
        else:
            print("⚠️  CUDA不可用，将使用CPU（速度较慢）")
    except ImportError:
        print("⚠️  PyTorch未安装，无法检查GPU")
    
    return True

def check_files():
    """检查必要文件"""
    print("\n🔍 检查项目文件...")
    
    required_files = [
        "livetalking_backend.py",
        "frontend_with_backend.py",
        "requirements_backend.txt"
    ]
    
    all_present = True
    for file in required_files:
        if Path(file).exists():
            print(f"✅ {file}")
        else:
            print(f"❌ {file} 缺失")
            all_present = False
    
    return all_present

def main():
    """主函数"""
    print("=" * 50)
    print("   LiveTalking 系统配置检查")
    print("=" * 50)
    
    results = []
    
    # 运行所有检查
    results.append(("Python", check_python()))
    results.append(("依赖包", check_packages()))
    results.append(("项目文件", check_files()))
    results.append(("LiveTalking", check_livetalking()))
    results.append(("FFmpeg", check_ffmpeg()))
    results.append(("端口", check_ports()))
    results.append(("GPU", check_gpu()))
    
    # 总结
    print("\n" + "=" * 50)
    print("   检查结果总结")
    print("=" * 50)
    
    critical_pass = True
    for name, result in results:
        if name in ["Python", "依赖包", "项目文件", "LiveTalking"]:
            if not result:
                critical_pass = False
            status = "✅" if result else "❌"
        else:
            status = "✅" if result else "⚠️"
        
        print(f"{status} {name}")
    
    print("\n" + "=" * 50)
    
    if critical_pass:
        print("✅ 系统检查通过，可以启动！")
        print("\n运行以下命令启动系统:")
        print("  python start_system_complete.py")
        print("\n或双击运行:")
        print("  start_windows.bat")
    else:
        print("❌ 存在关键问题，请先解决上述错误")
    
    print("=" * 50)

if __name__ == "__main__":
    main()
    input("\n按Enter键退出...")
