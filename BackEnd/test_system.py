"""
LiveTalking 系统测试脚本
快速检查系统是否正常
"""

import os
import requests
import time

# 配置
LIVETALKING_PATH = r"D:\Projects\See You Again\src\LiveTalking\LiveTalking-main"
BACKEND_URL = "http://localhost:8000"

def check_directories():
    """检查必要目录"""
    print("\n=== 检查目录 ===")
    
    dirs = {
        "数字人目录": os.path.join(LIVETALKING_PATH, "data", "avatars"),
        "音频目录": os.path.join(LIVETALKING_PATH, "wav"),
        "训练输出": os.path.join(LIVETALKING_PATH, "wav2lip", "results", "avatars"),
    }
    
    for name, path in dirs.items():
        if os.path.exists(path):
            count = len(os.listdir(path))
            print(f"✅ {name}: {path} ({count} 个文件/文件夹)")
        else:
            print(f"❌ {name}: 不存在")

def check_avatars():
    """检查已有数字人"""
    print("\n=== 已有数字人 ===")
    
    avatars_dir = os.path.join(LIVETALKING_PATH, "data", "avatars")
    if os.path.exists(avatars_dir):
        avatars = [d for d in os.listdir(avatars_dir) if d.startswith("wav2lip256_")]
        
        for avatar in avatars:
            # 检查音频
            wav_file = os.path.join(LIVETALKING_PATH, "wav", f"{avatar}.wav")
            has_audio = "🔊" if os.path.exists(wav_file) else "🔇"
            print(f"  {has_audio} {avatar}")
    else:
        print("  目录不存在")

def test_backend():
    """测试后端API"""
    print("\n=== 测试后端API ===")
    
    try:
        # 健康检查
        response = requests.get(f"{BACKEND_URL}/health", timeout=2)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 后端正常")
            print(f"  - 数字人: {data['avatars_count']} 个")
            print(f"  - 运行中: {data['running_count']} 个")
            print(f"  - 训练中: {data['training_count']} 个")
        else:
            print(f"❌ 后端响应异常: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("❌ 后端未启动")
    except Exception as e:
        print(f"❌ 错误: {e}")

def test_avatars_api():
    """测试获取数字人列表"""
    print("\n=== 数字人列表API ===")
    
    try:
        response = requests.get(f"{BACKEND_URL}/avatars", timeout=2)
        if response.status_code == 200:
            avatars = response.json()["avatars"]
            print(f"✅ 获取成功，共 {len(avatars)} 个数字人:")
            for avatar in avatars:
                status = "🟢运行中" if avatar["is_running"] else "⚪就绪"
                audio = "🔊" if avatar["has_audio"] else "🔇"
                print(f"  {status} {audio} {avatar['name']} ({avatar['id']})")
        else:
            print(f"❌ API响应异常: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到后端")
    except Exception as e:
        print(f"❌ 错误: {e}")

def check_files():
    """检查必要文件"""
    print("\n=== 检查文件 ===")
    
    files = {
        "app.py": os.path.join(LIVETALKING_PATH, "app.py"),
        "genavatar.py": os.path.join(LIVETALKING_PATH, "wav2lip", "genavatar.py"),
    }
    
    for name, path in files.items():
        if os.path.exists(path):
            print(f"✅ {name}")
        else:
            print(f"❌ {name} 不存在: {path}")

def main():
    """主函数"""
    print("=" * 50)
    print("   LiveTalking 系统测试")
    print("=" * 50)
    
    # 1. 检查目录
    check_directories()
    
    # 2. 检查文件
    check_files()
    
    # 3. 检查已有数字人
    check_avatars()
    
    # 4. 测试后端
    test_backend()
    
    # 5. 测试API
    test_avatars_api()
    
    print("\n" + "=" * 50)
    print("测试完成！")
    
    # 总结
    print("\n=== 建议 ===")
    print("1. 如果后端未启动，运行: python backend_simple.py")
    print("2. 如果前端未启动，运行: python frontend_simple.py")
    print("3. 如果缺少音频文件（🔇），需要为该数字人添加WAV文件")
    print("=" * 50)

if __name__ == "__main__":
    main()
    input("\n按Enter键退出...")
