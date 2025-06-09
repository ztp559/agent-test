import subprocess
import os

def play_audio(file_path="./demo.raw"):
    """
    使用ffplay播放音频文件
    参数:
        file_path: 音频文件路径，默认为"./demo.mp3"
    返回:
        bool: 播放成功返回True，失败返回False
    """
    try:
        # 检查ffplay是否安装
        subprocess.run(["ffplay", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("错误: 未找到ffplay命令，请先安装ffmpeg")
        print("安装命令: sudo apt install ffmpeg")
        return False
    
    # 检查文件是否存在
    if not os.path.exists(file_path):
        print(f"错误: 文件不存在 - {file_path}")
        return False
    
    try:
        print(f"正在播放: {file_path}")
        print("按Ctrl+C停止播放...")
        
        # ffplay播放命令
        cmd = [
            "ffplay",
            "-nodisp",          # 禁用显示窗口
            "-autoexit",        # 播放完成后自动退出
            "-infbuf",          # 无限输入缓冲区（适合实时流）
            "-ar", "24000",     # 设置音频采样率
            "-af", "anlmdn",    # 突发杂音过滤
            "-f", "s16le",      # 强制输入格式为16位小端无符号PCM音频
            file_path
        ]
        
        # 恢复播放命令，但使用不同的方式避免按键冲突
        process = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        process.wait()  # 等待播放完成
        print("播放完成")
        return True
        
    except KeyboardInterrupt:
        print("\n播放已停止")
        return True
    except subprocess.CalledProcessError as e:
        print(f"播放失败: {e}")
        return False
    except Exception as e:
        print(f"发生错误: {e}")
        return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="使用ffplay播放音频文件")
    parser.add_argument("-f", "--file", default="./demo.raw", 
                       help="音频文件路径 (默认: ./demo.mp3)")
    args = parser.parse_args()
    
    play_audio(args.file)