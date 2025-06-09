#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能文本转语音模块
支持流式文本输入和高质量语音合成
"""

import websocket
import datetime
import hashlib
import base64
import hmac
import json
import time
import ssl
import threading
import queue
import os
from urllib.parse import urlencode
from wsgiref.handlers import format_date_time
from datetime import datetime
from time import mktime
from typing import Optional, Dict, Any

# 尝试加载环境变量
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# TTS配置常量
TTS_CONFIG = {
    "voice": "x5_lingxiaoyue_flow",  # 语音模型
    "volume": 50,                    # 音量
    "speed": 50,                     # 语速
    "pitch": 50,                     # 音调
    "sample_rate": 24000,            # 采样率
    "channels": 1,                   # 声道数
    "bit_depth": 16,                 # 位深
    "encoding": "raw",               # 编码格式
    "buffer_timeout": 5.0,           # 缓冲区超时
    "send_interval": 1.0,            # 发送间隔
    "max_buffer_size": 500           # 最大缓冲区大小
}

# 全局状态管理
class TTSState:
    """TTS状态管理类"""
    def __init__(self):
        self.reset()
    
    def reset(self):
        self.text_queue = queue.Queue()
        self.audio_buffer = queue.Queue()
        self.ws_closed = False
        self.ws_error = False
        self.ws_instance = None
        self.ws_param = None
        self.current_filepath = None
        self.audio_writer_thread = None
        self.audio_writing_finished = False

# 全局状态实例
_tts_state = TTSState()


class WebSocketParams:
    """
    WebSocket连接参数配置类
    """
    
    def __init__(self, app_id: str, api_key: str, api_secret: str):
        self.app_id = app_id
        self.api_key = api_key
        self.api_secret = api_secret
        
        # 通用参数
        self.common_args = {"app_id": self.app_id, "status": 0}
        
        # 业务参数
        self.business_args = {
            "tts": {
                "vcn": TTS_CONFIG["voice"],
                "volume": TTS_CONFIG["volume"],
                "speed": TTS_CONFIG["speed"],
                "pitch": TTS_CONFIG["pitch"],
                "audio": {
                    "encoding": TTS_CONFIG["encoding"],
                    "sample_rate": TTS_CONFIG["sample_rate"],
                    "channels": TTS_CONFIG["channels"],
                    "bit_depth": TTS_CONFIG["bit_depth"],
                    "frame_size": 0
                }
            }
        }
    
    def create_data_frame(self, text: str, status: int, seq: int) -> Dict[str, Any]:
        """
        创建数据帧
        
        Args:
            text (str): 文本内容
            status (int): 状态码
            seq (int): 序列号
        
        Returns:
            Dict: 数据帧
        """
        return {
            "text": {
                "encoding": "utf8",
                "compress": "raw",
                "format": "plain",
                "status": status,
                "seq": seq,
                "text": base64.b64encode(text.encode('utf-8')).decode("UTF8")
            }
        }


def _create_auth_url(request_url: str, method: str = "GET", 
                    api_key: str = "", api_secret: str = "") -> str:
    """
    创建WebSocket认证URL
    
    Args:
        request_url (str): 请求URL
        method (str): HTTP方法
        api_key (str): API密钥
        api_secret (str): API密钥
    
    Returns:
        str: 认证后的URL
    """
    # 解析URL
    schema_end = request_url.index("://")
    host_start = schema_end + 3
    path_start = request_url.index("/", host_start)
    
    host = request_url[host_start:path_start]
    path = request_url[path_start:]
    
    # 生成时间戳
    now = datetime.now()
    date = format_date_time(mktime(now.timetuple()))
    
    # 构建签名
    signature_origin = f"host: {host}\ndate: {date}\n{method} {path} HTTP/1.1"
    signature_sha = hmac.new(
        api_secret.encode('utf-8'),
        signature_origin.encode('utf-8'),
        digestmod=hashlib.sha256
    ).digest()
    signature_sha = base64.b64encode(signature_sha).decode('utf-8')
    
    # 构建授权
    authorization_origin = (
        f'api_key="{api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature_sha}"'
    )
    authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode('utf-8')
    
    # 构建参数
    values = {
        "host": host,
        "date": date,
        "authorization": authorization
    }
    
    return f"{request_url}?{urlencode(values)}"


def _audio_writer_worker() -> None:
    """
    音频写入工作线程
    处理音频缓冲区中的数据并写入文件
    """
    global _tts_state
    
    try:
        # 清理已存在的文件
        if os.path.exists(_tts_state.current_filepath):
            os.remove(_tts_state.current_filepath)
        
        audio_data_received = False
        
        with open(_tts_state.current_filepath, 'ab') as f:
            while True:
                try:
                    # 从缓冲区获取音频数据
                    audio_data = _tts_state.audio_buffer.get(timeout=TTS_CONFIG["buffer_timeout"])
                    
                    if audio_data is None:  # 结束信号
                        break
                    
                    # 写入音频数据
                    f.write(audio_data)
                    f.flush()
                    audio_data_received = True
                    
                except queue.Empty:
                    # 检查是否应该结束
                    if _tts_state.ws_closed and _tts_state.audio_buffer.empty():
                        break
                    continue
                except Exception as e:
                    print(f"音频写入错误: {e}")
                    break
        
        # 验证文件
        if audio_data_received and os.path.exists(_tts_state.current_filepath):
            file_size = os.path.getsize(_tts_state.current_filepath)
            print(f"音频文件生成完成: {_tts_state.current_filepath} ({file_size} bytes)")
        else:
            print("警告: 音频文件生成失败")
            
    except Exception as e:
        print(f"音频写入线程错误: {e}")
    finally:
        _tts_state.audio_writing_finished = True


def _on_message(ws, message: str) -> None:
    """
    处理WebSocket消息
    """
    global _tts_state
    
    try:
        data = json.loads(message)
        code = data["header"]["code"]
        
        if code != 0:
            error_msg = data.get("message", "未知错误")
            print(f"TTS错误: {error_msg} (code: {code})")
            _tts_state.ws_error = True
            _tts_state.audio_buffer.put(None)  # 发送结束信号
            return
        
        # 处理音频数据
        payload = data.get("payload")
        if payload and "audio" in payload:
            audio_data = base64.b64decode(payload["audio"]["audio"])
            status = payload["audio"]["status"]
            
            if len(audio_data) > 0:
                _tts_state.audio_buffer.put(audio_data)
            
            if status == 2:  # 结束状态
                _tts_state.audio_buffer.put(None)
                _tts_state.ws_closed = True
                ws.close()
                
    except Exception as e:
        print(f"消息处理错误: {e}")
        _tts_state.ws_error = True
        _tts_state.audio_buffer.put(None)


def _on_error(ws, error) -> None:
    """
    处理WebSocket错误
    """
    global _tts_state
    print(f"WebSocket错误: {error}")
    _tts_state.ws_error = True


def _on_close(ws, close_status_code, close_msg) -> None:
    """
    处理WebSocket关闭
    """
    global _tts_state
    _tts_state.ws_closed = True
    if not _tts_state.audio_writing_finished:
        _tts_state.audio_buffer.put(None)


def _on_open(ws) -> None:
    """
    处理WebSocket开启，开始文本处理
    """
    def text_sender():
        global _tts_state
        
        seq = 0
        text_buffer = ""
        last_send_time = time.time()
        
        while not _tts_state.ws_closed and not _tts_state.ws_error:
            try:
                # 获取文本块
                try:
                    text_chunk = _tts_state.text_queue.get(timeout=0.1)
                    
                    if text_chunk is None:  # 结束信号
                        # 发送剩余文本
                        if text_buffer.strip():
                            _send_text_frame(ws, text_buffer, 0 if seq == 0 else 1, seq)
                            seq += 1
                        
                        # 发送结束帧
                        _send_text_frame(ws, "。", 2, seq)
                        break
                    
                    text_buffer += text_chunk
                    
                except queue.Empty:
                    pass
                
                # 检查是否需要发送
                current_time = time.time()
                should_send = False
                
                if text_buffer.strip():
                    if (current_time - last_send_time >= TTS_CONFIG["send_interval"] or 
                        len(text_buffer) > TTS_CONFIG["max_buffer_size"]):
                        should_send = True
                
                if should_send:
                    status = 0 if seq == 0 else 1
                    _send_text_frame(ws, text_buffer, status, seq)
                    text_buffer = ""
                    last_send_time = current_time
                    seq += 1
                    
            except Exception as e:
                print(f"文本发送错误: {e}")
                _tts_state.ws_error = True
                break
    
    threading.Thread(target=text_sender, daemon=True).start()


def _send_text_frame(ws, text: str, status: int, seq: int) -> None:
    """
    发送文本帧
    """
    global _tts_state
    
    data_frame = _tts_state.ws_param.create_data_frame(text, status, seq)
    packet = {
        "header": _tts_state.ws_param.common_args.copy(),
        "parameter": _tts_state.ws_param.business_args,
        "payload": data_frame,
    }
    packet["header"]["status"] = status
    
    ws.send(json.dumps(packet))


def stream_text_to_speech_init(app_id: str, api_secret: str, api_key: str, 
                              filepath: str = './demo.raw') -> bool:
    """
    初始化流式文本转语音连接
    
    Args:
        app_id (str): 应用ID
        api_secret (str): API密钥
        api_key (str): API密钥
        filepath (str): 输出音频文件路径
    
    Returns:
        bool: 初始化成功返回True
    """
    global _tts_state
    
    # 重置状态
    _tts_state.reset()
    _tts_state.current_filepath = filepath
    
    try:
        # 创建WebSocket参数
        _tts_state.ws_param = WebSocketParams(app_id, api_key, api_secret)
        
        # 创建WebSocket URL
        request_url = 'wss://cbm01.cn-huabei-1.xf-yun.com/v1/private/mcd9m97e6'
        ws_url = _create_auth_url(request_url, "GET", api_key, api_secret)
        
        # 启动音频写入线程
        _tts_state.audio_writer_thread = threading.Thread(
            target=_audio_writer_worker, daemon=True
        )
        _tts_state.audio_writer_thread.start()
        
        # 创建WebSocket连接
        _tts_state.ws_instance = websocket.WebSocketApp(
            ws_url,
            on_message=_on_message,
            on_error=_on_error,
            on_close=_on_close,
            on_open=_on_open
        )
        
        # 启动WebSocket连接
        ws_thread = threading.Thread(
            target=lambda: _tts_state.ws_instance.run_forever(
                sslopt={"cert_reqs": ssl.CERT_NONE}
            ),
            daemon=True
        )
        ws_thread.start()
        
        # 等待连接建立
        timeout = 10
        start_time = time.time()
        while (_tts_state.ws_instance.sock is None and 
               not _tts_state.ws_error and 
               (time.time() - start_time) < timeout):
            time.sleep(0.1)
        
        if _tts_state.ws_instance.sock is not None:
            print("TTS连接已建立")
            return True
        else:
            print("TTS连接建立失败")
            return False
            
    except Exception as e:
        print(f"TTS初始化错误: {e}")
        return False


def stream_text_to_speech_send(text_chunk: str) -> bool:
    """
    发送文本块到TTS服务
    
    Args:
        text_chunk (str): 文本块内容
    
    Returns:
        bool: 发送成功返回True
    """
    global _tts_state
    
    if _tts_state.ws_closed or _tts_state.ws_error:
        print("TTS连接已关闭，无法发送文本")
        return False
    
    try:
        if text_chunk and text_chunk.strip():
            _tts_state.text_queue.put(text_chunk)
        return True
    except Exception as e:
        print(f"文本发送错误: {e}")
        return False


def stream_text_to_speech_finish() -> bool:
    """
    结束流式文本转语音
    
    Returns:
        bool: 完成成功返回True
    """
    global _tts_state
    
    try:
        # 发送结束信号
        _tts_state.text_queue.put(None)
        
        # 等待处理完成
        timeout = 30
        start_time = time.time()
        while (not _tts_state.ws_closed and 
               not _tts_state.ws_error and 
               (time.time() - start_time) < timeout):
            time.sleep(0.1)
        
        # 等待音频写入完成
        if (_tts_state.audio_writer_thread and 
            _tts_state.audio_writer_thread.is_alive()):
            _tts_state.audio_writer_thread.join(timeout=10)
        
        return _tts_state.audio_writing_finished
        
    except Exception as e:
        print(f"TTS结束错误: {e}")
        return False


def text_to_speech(text: str, app_id: str, api_secret: str, api_key: str, 
                  filepath: str = './demo.raw') -> bool:
    """
    一次性文本转语音函数
    
    Args:
        text (str): 要转换的文本
        app_id (str): 应用ID
        api_secret (str): API密钥
        api_key (str): API密钥
        filepath (str): 输出音频文件路径
    
    Returns:
        bool: 转换成功返回True
    """
    if not stream_text_to_speech_init(app_id, api_secret, api_key, filepath):
        return False
    
    if not stream_text_to_speech_send(text):
        return False
    
    return stream_text_to_speech_finish()


if __name__ == "__main__":
    # 从环境变量获取配置
    app_id = os.environ.get("appid")
    api_secret = os.environ.get("apisecret")
    api_key = os.environ.get("apikey")
    
    if not all([app_id, api_secret, api_key]):
        print("错误: 请设置环境变量 appid, apisecret, apikey")
        exit(1)
    
    # 测试流式TTS
    print("测试流式文本转语音...")
    
    if stream_text_to_speech_init(app_id, api_secret, api_key, './demo.raw'):
        test_chunks = ["这是第一段文本，", "这是第二段文本，", "这是最后一段文本。"]
        
        for chunk in test_chunks:
            if stream_text_to_speech_send(chunk):
                print(f"发送成功: {chunk}")
                time.sleep(0.5)
            else:
                print(f"发送失败: {chunk}")
                break
        
        result = stream_text_to_speech_finish()
        print(f"转换结果: {'成功' if result else '失败'}")
    else:
        print("初始化失败")
