#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
音频播放模块
使用ffplay播放音频文件，支持多种音频格式
"""

import subprocess
import os
from typing import Optional


def play_audio(file_path: str = "./demo.raw") -> bool:
    """
    使用ffplay播放音频文件
    
    Args:
        file_path (str): 音频文件路径
    
    Returns:
        bool: 播放成功返回True，失败返回False
    
    Raises:
        FileNotFoundError: 当ffplay未安装或文件不存在时
    """
    # 快速检查文件是否存在，避免后续无效操作
    if not os.path.isfile(file_path):
        print(f"错误: 文件不存在 - {file_path}")
        return False
    
    # 检查ffplay是否可用（仅检查一次，提高性能）
    try:
        subprocess.run(["ffplay", "-version"], 
                      capture_output=True, check=True, timeout=3)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        print("错误: 未找到ffplay命令，请安装ffmpeg: sudo apt install ffmpeg")
        return False
    
    try:
        print(f"正在播放: {file_path}")
        
        # 优化的ffplay命令参数
        cmd = [
            "ffplay",
            "-nodisp",          # 禁用视频显示窗口
            "-autoexit",        # 播放完成后自动退出
            "-loglevel", "quiet",  # 减少日志输出
            "-ar", "24000",     # 音频采样率
            "-f", "s16le",      # 音频格式
            file_path
        ]
        
        # 使用Popen避免阻塞，重定向所有输出提高性能
        with subprocess.Popen(cmd, 
                             stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, 
                             stderr=subprocess.DEVNULL) as process:
            process.wait()  # 等待播放完成
        
        print("播放完成")
        return True
        
    except KeyboardInterrupt:
        print("\n播放已停止")
        return True
    except Exception as e:
        print(f"播放失败: {e}")
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="音频播放工具")
    parser.add_argument("-f", "--file", default="./demo.raw", 
                       help="音频文件路径 (默认: ./demo.raw)")
    args = parser.parse_args()
    
    success = play_audio(args.file)
    exit(0 if success else 1)