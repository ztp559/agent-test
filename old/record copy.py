import subprocess
import os
import time

def record_audio(output_path="./origin_audio.raw"):
    """
    使用sox录制音频
    参数:
        output_path: 输出文件路径，默认为"./origin_audio.raw"
    返回:
        bool: 录制成功返回True，失败返回False
    """
    try:
        # 检查sox是否安装
        subprocess.run(["sox", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("错误: 未找到sox命令，请先安装sox")
        return False
    
    try:
        # 创建输出目录
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # 如果文件已存在，删除它以允许覆盖
        if os.path.exists(output_path):
            os.remove(output_path)
            print(f"已删除现有文件: {output_path}")
        
        print(f"开始录音，按任意键停止录音...")
        print(f"输出文件: {output_path}")
        
        # sox录音命令: 采样率16k、16bit、单声道、PCM格式
        cmd = [
            "sox", "-d",  # -q 禁用进度输出，-d 默认输入设备
            "-r", "16000",  # 采样率16kHz
            "-b", "16",     # 位深16bit
            "-c", "1",      # 单声道
            "-e", "signed-integer",  # PCM格式
            output_path
        ]
        
        # 启动录音进程
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        
        # 等待用户按键
        input("")
        
        # 终止录音进程
        process.terminate()
        return_code = process.wait()
        
        # 检查录音进程是否有错误
        if return_code != 0 and return_code != -15:  # -15是SIGTERM正常终止
            stderr_output = process.stderr.read().decode() if process.stderr else ""
            print(f"录音进程异常退出，返回码: {return_code}")
            if stderr_output:
                print(f"错误信息: {stderr_output}")
            return False
        
        # 验证录音文件是否生成
        if not os.path.exists(output_path):
            print(f"错误: 录音文件未生成 - {output_path}")
            return False
        
        # 验证文件大小（至少应该有一些数据）
        file_size = os.path.getsize(output_path)
        # 验证文件是否为有效的音频文件（简单检查）
        min_size = 1024  # 最小1KB，对应约0.03秒的16kHz 16bit单声道音频
        if file_size < min_size:
            print(f"警告: 录音文件过小 ({file_size} bytes)，可能录音时间太短")
            print(f"建议录音时间至少1秒以上")      
        print(f"录音完成，文件保存至: {output_path}")
        return True
        
    except KeyboardInterrupt:
        print("\n录音已停止")
        if 'process' in locals():
            process.terminate()
            process.wait()
        # 即使被中断，也要验证文件是否生成
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except subprocess.CalledProcessError as e:
        print(f"录音失败: {e}")
        return False
    except Exception as e:
        print(f"发生错误: {e}")
        if 'process' in locals():
            process.terminate()
            process.wait()
        return False

if __name__ == "__main__":  # 检查脚本是否作为主程序运行（而不是被导入为模块）
    import argparse  # 导入命令行参数解析库
    parser = argparse.ArgumentParser(description="使用sox录制音频")  # 创建命令行参数解析器对象，设置程序描述
    parser.add_argument("-o", "--output", default="./origin_audio.raw",   # 添加输出文件路径参数，短选项-o，长选项--output
                       help="输出文件路径 (默认: ./origin_audio.raw)")  # 设置默认值和帮助信息
    args = parser.parse_args()  # 解析命令行参数并存储到args对象中
    
    success = record_audio(args.output)  # 调用录音函数，传入解析得到的输出文件路径参数
    if success:
        print("录音成功完成")
    else:
        print("录音失败")
        exit(1)