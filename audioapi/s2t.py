#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
语音转文本模块
基于WebSocket的实时语音识别服务
"""

import _thread as thread
import time
import websocket
import base64
import datetime
import hashlib
import hmac
import json
import ssl
import threading
import os
import sys
from datetime import datetime
from time import mktime
from urllib.parse import urlencode
from wsgiref.handlers import format_date_time
from typing import Optional

# 添加父目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from voiceIO.record import record_audio

# 音频帧状态常量
STATUS_FIRST_FRAME = 0
STATUS_CONTINUE_FRAME = 1
STATUS_LAST_FRAME = 2

# 音频处理配置
AUDIO_CONFIG = {
    "frame_size": 1280,        # 每帧音频大小
    "interval": 0.04,          # 发送间隔(秒)
    "sample_rate": 16000,      # 采样率
    "encoding": "raw",         # 编码格式
    "timeout": 30              # 默认超时时间
}


class WebSocketParams:
    """
    WebSocket连接参数配置类
    """
    
    def __init__(self, app_id: str, api_key: str, api_secret: str, audio_file: str):
        self.app_id = app_id
        self.api_key = api_key
        self.api_secret = api_secret
        self.audio_file = audio_file
        
        # 识别参数配置
        self.iat_params = {
            "domain": "slm",
            "language": "zh_cn",
            "accent": "mandarin",
            "dwa": "wpgs",
            "result": {
                "encoding": "utf8",
                "compress": "raw",
                "format": "plain"
            }
        }
    
    def create_url(self) -> str:
        """
        生成WebSocket认证URL
        
        Returns:
            str: 认证后的WebSocket URL
        """
        url = 'ws://iat.xf-yun.com/v1'
        
        # 生成时间戳
        now = datetime.now()
        date = format_date_time(mktime(now.timetuple()))
        
        # 构建签名字符串
        signature_origin = f"host: iat.xf-yun.com\ndate: {date}\nGET /v1 HTTP/1.1"
        
        # HMAC-SHA256加密
        signature_sha = hmac.new(
            self.api_secret.encode('utf-8'),
            signature_origin.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        signature_sha = base64.b64encode(signature_sha).decode('utf-8')
        
        # 构建授权字符串
        authorization_origin = (
            f'api_key="{self.api_key}", algorithm="hmac-sha256", '
            f'headers="host date request-line", signature="{signature_sha}"'
        )
        authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode('utf-8')
        
        # 构建URL参数
        params = {
            "authorization": authorization,
            "date": date,
            "host": "iat.xf-yun.com"
        }
        
        return f"{url}?{urlencode(params)}"


class SpeechRecognizer:
    """
    语音识别器类
    提供完整的语音识别功能
    """
    
    def __init__(self, app_id: str, api_key: str, api_secret: str):
        self.app_id = app_id
        self.api_key = api_key
        self.api_secret = api_secret
        
        # 识别状态
        self.final_result = ""
        self.latest_result = ""
        self.recognition_complete = False
        self.error_occurred = False
        self.error_message = ""
    
    def _reset_state(self) -> None:
        """重置识别状态"""
        self.final_result = ""
        self.latest_result = ""
        self.recognition_complete = False
        self.error_occurred = False
        self.error_message = ""
    
    def _on_message(self, ws, message: str) -> None:
        """处理WebSocket消息"""
        try:
            data = json.loads(message)
            code = data["header"]["code"]
            status = data["header"]["status"]
            
            if code != 0:
                self.error_occurred = True
                self.error_message = f"识别错误: {code}"
                ws.close()
                return
            
            # 处理识别结果
            payload = data.get("payload")
            if payload and "result" in payload:
                text_data = json.loads(
                    base64.b64decode(payload["result"]["text"]).decode("utf8")
                )
                
                # 提取文本内容
                result = ""
                for ws_item in text_data.get("ws", []):
                    for cw_item in ws_item.get("cw", []):
                        result += cw_item.get("w", "")
                
                # 更新结果（只保留更长的结果）
                if len(result) > len(self.latest_result):
                    self.latest_result = result
            
            # 检查是否完成
            if status == 2:
                self.final_result = self.latest_result
                self.recognition_complete = True
                ws.close()
                
        except Exception as e:
            self.error_occurred = True
            self.error_message = f"消息处理错误: {e}"
            ws.close()
    
    def _on_error(self, ws, error) -> None:
        """处理WebSocket错误"""
        self.error_occurred = True
        self.error_message = f"WebSocket错误: {error}"
    
    def _on_close(self, ws, close_status_code, close_msg) -> None:
        """处理WebSocket关闭"""
        pass
    
    def _on_open(self, ws, audio_file: str) -> None:
        """处理WebSocket开启，开始发送音频数据"""
        def send_audio():
            try:
                ws_param = WebSocketParams(self.app_id, self.api_key, self.api_secret, audio_file)
                status = STATUS_FIRST_FRAME
                
                with open(audio_file, "rb") as fp:
                    while True:
                        # 读取音频数据
                        buf = fp.read(AUDIO_CONFIG["frame_size"])
                        if not buf:
                            status = STATUS_LAST_FRAME
                        
                        # 编码音频数据
                        audio_data = base64.b64encode(buf).decode('utf-8')
                        
                        # 构建数据包
                        packet = {
                            "header": {
                                "status": 0 if status == STATUS_FIRST_FRAME else (1 if status == STATUS_CONTINUE_FRAME else 2),
                                "app_id": ws_param.app_id
                            },
                            "parameter": {"iat": ws_param.iat_params} if status == STATUS_FIRST_FRAME else {},
                            "payload": {
                                "audio": {
                                    "audio": audio_data,
                                    "sample_rate": AUDIO_CONFIG["sample_rate"],
                                    "encoding": AUDIO_CONFIG["encoding"]
                                }
                            }
                        }
                        
                        # 发送数据
                        ws.send(json.dumps(packet))
                        
                        if status == STATUS_LAST_FRAME:
                            break
                        
                        # 更新状态
                        if status == STATUS_FIRST_FRAME:
                            status = STATUS_CONTINUE_FRAME
                        
                        # 控制发送频率
                        time.sleep(AUDIO_CONFIG["interval"])
                        
            except Exception as e:
                self.error_occurred = True
                self.error_message = f"音频发送错误: {e}"
        
        thread.start_new_thread(send_audio, ())
    
    def recognize_audio(self, audio_file: str, timeout: int = AUDIO_CONFIG["timeout"]) -> str:
        """
        识别音频文件
        
        Args:
            audio_file (str): 音频文件路径
            timeout (int): 超时时间(秒)
        
        Returns:
            str: 识别结果文本
        """
        self._reset_state()
        
        # 检查音频文件
        if not os.path.exists(audio_file):
            return f"音频文件不存在: {audio_file}"
        
        try:
            # 创建WebSocket连接
            ws_param = WebSocketParams(self.app_id, self.api_key, self.api_secret, audio_file)
            websocket.enableTrace(False)
            ws_url = ws_param.create_url()
            
            ws = websocket.WebSocketApp(
                ws_url,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close
            )
            ws.on_open = lambda ws: self._on_open(ws, audio_file)
            
            # 启动WebSocket连接
            ws_thread = threading.Thread(
                target=lambda: ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}),
                daemon=True
            )
            ws_thread.start()
            
            # 等待识别完成
            start_time = time.time()
            while not self.recognition_complete and not self.error_occurred:
                if time.time() - start_time > timeout:
                    ws.close()
                    return "识别超时"
                time.sleep(0.1)
            
            return self.error_message if self.error_occurred else self.final_result
            
        except Exception as e:
            return f"识别失败: {e}"


def recognize_speech(audio_file: str, 
                    app_id: str = None,
                    api_secret: str = None, 
                    api_key: str = None,
                    timeout: int = AUDIO_CONFIG["timeout"]) -> str:
    """
    语音识别便捷函数
    
    Args:
        audio_file (str): 音频文件路径
        app_id (str): 应用ID，为None时从环境变量获取
        api_secret (str): API密钥，为None时从环境变量获取
        api_key (str): API Key，为None时从环境变量获取
        timeout (int): 超时时间(秒)
    
    Returns:
        str: 识别结果
    """
    # 从环境变量获取配置
    if not app_id:
        app_id = os.environ.get('s2t_appid', '15a90977')
    if not api_secret:
        api_secret = os.environ.get('s2t_api_secret', 'MmVjMzA4NDExYTgxMzAzYjUxYzFjMDM5')
    if not api_key:
        api_key = os.environ.get('s2t_api_key', '64acce84dee079661249e08083636471')
    
    recognizer = SpeechRecognizer(app_id, api_key, api_secret)
    return recognizer.recognize_audio(audio_file, timeout)


if __name__ == "__main__":
    # 测试代码
    audio_file = '/home/duduzhang/agent/origin_audio.raw'
    
    print("开始录音...")
    if record_audio(audio_file):
        print("开始语音识别...")
        result = recognize_speech(audio_file)
        print(f"识别结果: {result}")
    else:
        print("录音失败")
