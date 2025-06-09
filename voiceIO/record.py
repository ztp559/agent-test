#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
音频录制模块
使用sox录制高质量音频，支持实时录制和按键停止
"""

import subprocess
import os
from typing import Optional

# 音频录制配置常量
AUDIO_CONFIG = {
    "sample_rate": "16000",    # 采样率16kHz
    "bit_depth": "16",         # 位深16bit
    "channels": "1",           # 单声道
    "encoding": "signed-integer",  # PCM格式
    "min_file_size": 1024      # 最小文件大小(字节)
}


def record_audio(output_path: str = "./origin_audio.raw") -> bool:
    """
    使用sox录制音频
    
    Args:
        output_path (str): 输出文件路径
    
    Returns:
        bool: 录制成功返回True，失败返回False
    """
    # 检查sox是否可用
    try:
        subprocess.run(["sox", "--version"], 
                      capture_output=True, check=True, timeout=3)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        print("错误: 未找到sox命令，请安装sox")
        return False
    
    # 准备输出目录
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    # 清理已存在的文件
    if os.path.exists(output_path):
        os.remove(output_path)
        print(f"已删除现有文件: {output_path}")
    
    print(f"开始录音，按回车键停止...")
    print(f"输出文件: {output_path}")
    
    # 构建sox录音命令
    cmd = [
        "sox", "-d",  # 使用默认输入设备
        "-r", AUDIO_CONFIG["sample_rate"],
        "-b", AUDIO_CONFIG["bit_depth"],
        "-c", AUDIO_CONFIG["channels"],
        "-e", AUDIO_CONFIG["encoding"],
        output_path
    ]
    
    process = None
    try:
        # 启动录音进程
        process = subprocess.Popen(cmd, 
                                 stdout=subprocess.DEVNULL, 
                                 stderr=subprocess.PIPE)
        
        # 等待用户按键
        input()
        
        # 终止录音
        process.terminate()
        return_code = process.wait(timeout=5)  # 添加超时避免死锁
        
        # 检查录音结果
        if return_code not in (0, -15):  # 0=正常退出, -15=SIGTERM
            stderr_output = process.stderr.read().decode() if process.stderr else ""
            print(f"录音进程异常退出，返回码: {return_code}")
            if stderr_output:
                print(f"错误信息: {stderr_output}")
            return False
        
        # 验证录音文件
        return _validate_audio_file(output_path)
        
    except KeyboardInterrupt:
        print("\n录音已停止")
        if process:
            process.terminate()
            process.wait(timeout=3)
        return _validate_audio_file(output_path)
        
    except Exception as e:
        print(f"录音失败: {e}")
        if process:
            process.terminate()
            process.wait(timeout=3)
        return False


def _validate_audio_file(file_path: str) -> bool:
    """
    验证录音文件的有效性
    
    Args:
        file_path (str): 音频文件路径
    
    Returns:
        bool: 文件有效返回True
    """
    if not os.path.exists(file_path):
        print(f"错误: 录音文件未生成 - {file_path}")
        return False
    
    file_size = os.path.getsize(file_path)
    if file_size < AUDIO_CONFIG["min_file_size"]:
        print(f"警告: 录音文件过小 ({file_size} bytes)，可能录音时间太短")
        print("建议录音时间至少1秒以上")
    
    print(f"录音完成，文件保存至: {file_path} ({file_size} bytes)")
    return True


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="音频录制工具")
    parser.add_argument("-o", "--output", default="./origin_audio.raw",
                       help="输出文件路径 (默认: ./origin_audio.raw)")
    args = parser.parse_args()
    
    success = record_audio(args.output)
    print("录音成功完成" if success else "录音失败")
    exit(0 if success else 1)