# -*- coding:utf-8 -*-

import websocket
import datetime
import hashlib
import base64
import hmac
import json
from urllib.parse import urlencode
import time
import ssl
from wsgiref.handlers import format_date_time
from datetime import datetime
from time import mktime
import _thread as thread
import os
import queue
import threading
import os
import logging

# 全局变量用于流式处理
text_queue = queue.Queue()
audio_buffer = queue.Queue()  # 新增音频缓冲队列
ws_closed = False
ws_error = False
ws_instance = None
wsParam = None
current_filepath = None
audio_writer_thread = None  # 音频写入线程
audio_writing_finished = False  # 音频写入完成标志

class Ws_Param(object):
    def __init__(self, APPID, APIKey, APISecret):
        self.APPID = APPID
        self.APIKey = APIKey
        self.APISecret = APISecret
        # 初始状态改为0，支持流式
        self.CommonArgs = {"app_id": self.APPID, "status": 0}
        self.BusinessArgs = {
            "tts": {
                "vcn": "x5_lingxiaoyue_flow",
                "volume": 50,
                "rhy": 1,
                "speed": 50,
                "pitch": 50,
                "bgs": 0,
                "reg": 0,
                "rdn": 0,
                "audio": {
                    "encoding": "raw",
                    "sample_rate": 24000,
                    "channels": 1,
                    "bit_depth": 16,
                    "frame_size": 0
                }
            }
        }
    
    def create_data_frame(self, text, status, seq):
        """创建数据帧"""
        return {
            "text": {
                "encoding": "utf8",
                "compress": "raw",
                "format": "plain",
                "status": status,
                "seq": seq,
                "text": str(base64.b64encode(text.encode('utf-8')), "UTF8")
            }
        }

class AssembleHeaderException(Exception):
    def __init__(self, msg):
        self.message = msg

class Url:
    def __init__(self, host, path, schema):
        self.host = host
        self.path = path
        self.schema = schema

def sha256base64(data):
    sha256 = hashlib.sha256()
    sha256.update(data)
    digest = base64.b64encode(sha256.digest()).decode(encoding='utf-8')
    return digest

def parse_url(requset_url):
    stidx = requset_url.index("://")
    host = requset_url[stidx + 3:]
    schema = requset_url[:stidx + 3]
    edidx = host.index("/")
    if edidx <= 0:
        raise AssembleHeaderException("invalid request url:" + requset_url)
    path = host[edidx:]
    host = host[:edidx]
    u = Url(host, path, schema)
    return u

def assemble_ws_auth_url(requset_url, method="GET", api_key="", api_secret=""):
    u = parse_url(requset_url)
    host = u.host
    path = u.path
    now = datetime.now()
    date = format_date_time(mktime(now.timetuple()))
    print(f"认证时间戳: {date}")  # 改进调试信息
    signature_origin = "host: {}\ndate: {}\n{} {} HTTP/1.1".format(host, date, method, path)
    signature_sha = hmac.new(api_secret.encode('utf-8'), signature_origin.encode('utf-8'),
                             digestmod=hashlib.sha256).digest()
    signature_sha = base64.b64encode(signature_sha).decode(encoding='utf-8')
    authorization_origin = "api_key=\"%s\", algorithm=\"%s\", headers=\"%s\", signature=\"%s\"" % (
        api_key, "hmac-sha256", "host date request-line", signature_sha)
    authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode(encoding='utf-8')
    values = {
        "host": host,
        "date": date,
        "authorization": authorization
    }
    return requset_url + "?" + urlencode(values)

# 在文件开头添加日志配置
def setup_logging():
    # 清空日志文件
    message_log_file = '/home/duduzhang/agent/audioapi/message_log.txt'
    send_log_file = '/home/duduzhang/agent/audioapi/send_log.txt'
    
    # 清空现有日志文件
    with open(message_log_file, 'w') as f:
        f.write('')
    with open(send_log_file, 'w') as f:
        f.write('')
    
    return message_log_file, send_log_file

# 在模块导入时初始化日志
message_log_file, send_log_file = setup_logging()

def audio_writer_worker():
    """独立的音频写入线程，处理音频缓冲区中的数据"""
    global audio_buffer, current_filepath, audio_writing_finished
    
    try:
        # 删除已存在的文件
        if os.path.exists(current_filepath):
            os.remove(current_filepath)
            print(f"删除已存在的{current_filepath}文件")
        
        audio_data_received = False  # 跟踪是否接收到音频数据
        
        with open(current_filepath, 'ab') as f:
            while True:
                try:
                    # 从缓冲区获取音频数据，超时5秒
                    audio_data = audio_buffer.get(timeout=5.0)
                    
                    if audio_data is None:  # 结束信号
                        print("音频写入线程收到结束信号")
                        break
                    
                    # 写入音频数据
                    f.write(audio_data)
                    f.flush()  # 确保数据立即写入磁盘
                    audio_data_received = True
                    print(f"写入音频数据: {len(audio_data)} 字节")
                    
                except queue.Empty:
                    # 如果WebSocket已关闭且缓冲区为空，结束写入
                    if ws_closed and audio_buffer.empty():
                        print("WebSocket已关闭且音频缓冲区为空，结束写入")
                        break
                    continue
                except Exception as e:
                    print(f"音频写入出错: {e}")
                    break
        
        # 检查文件是否有内容
        if audio_data_received and os.path.exists(current_filepath):
            file_size = os.path.getsize(current_filepath)
            print(f"音频文件写入完成，大小: {file_size} 字节")
        else:
            print("警告：没有接收到音频数据或文件写入失败")
    
    except Exception as e:
        print(f"音频写入线程出错: {e}")
    finally:
        audio_writing_finished = True
        print("音频写入线程已结束")

def on_message(ws, message):
    global ws_closed, ws_error, current_filepath, audio_buffer
    try:
        message = json.loads(message)
        code = message["header"]["code"]
        sid = message["header"]["sid"]
        print(f"解析消息 - code: {code}, sid: {sid}")
        
        # 首先检查错误码
        if code != 0:
            errMsg = message.get("message", "未知错误")
            print("错误: sid:%s call error:%s code is:%s" % (sid, errMsg, code))
            ws_error = True
            # 发送结束信号到音频缓冲区
            try:
                audio_buffer.put(None, timeout=1.0)
            except:
                pass
            return
        
        if("payload" in message):
            # 检查是否有pybuf字段（可能是调试信息）
            if "pybuf" in message["payload"] and "text" in message["payload"]["pybuf"]:
                revtext = base64.b64decode(message["payload"]["pybuf"]['text']).decode('utf-8')
                # 将打印改为写入日志文件
                with open(message_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"收到原始消息: {revtext}\n")
            
            # 处理音频数据
            if "audio" in message["payload"]:
                audio = message["payload"]["audio"]['audio']
                audio = base64.b64decode(audio)
                status = message["payload"]['audio']["status"]
                print(f"音频数据 - status: {status}, 长度: {len(audio)}")
                
                # 将音频数据放入缓冲区而不是直接写入文件
                if len(audio) > 0:  # 只有非空音频数据才放入缓冲区
                    audio_buffer.put(audio)
                
                if status == 2:
                    print("收到结束信号，关闭连接")
                    # 发送结束信号到音频缓冲区
                    try:
                        audio_buffer.put(None, timeout=1.0)
                    except:
                        pass
                    ws_closed = True
                    ws.close()
        else:
            print("消息中没有payload")
            # 如果是错误消息且没有payload，也应该结束音频写入
            if code != 0:
                try:
                    audio_buffer.put(None, timeout=1.0)
                except:
                    pass
    except Exception as e:
        print(f"解析消息异常: {e}")
        ws_error = True
        # 发送结束信号到音频缓冲区
        try:
            audio_buffer.put(None, timeout=1.0)
        except:
            pass

def on_error(ws, error):
    global ws_error
    print(f"WebSocket错误: {error}")
    ws_error = True

def on_close(ws, ts, end):
    global ws_closed, audio_buffer, audio_writing_finished
    ws_closed = True
    print("WebSocket连接已关闭")
    # 确保音频缓冲区收到结束信号
    if not audio_writing_finished:
        try:
            audio_buffer.put(None, timeout=1.0)
            print("已向音频缓冲区发送结束信号")
        except Exception as e:
            print(f"发送结束信号失败: {e}")

def on_open(ws):
    def run(*args):
        global text_queue, ws_closed, ws_error, wsParam, current_filepath
        
        # 不在这里删除文件，让音频写入线程处理
        
        seq = 0
        print("------>WebSocket连接已建立，等待文本流")
        
        # 文本累积缓冲区
        text_buffer = ""
        last_send_time = time.time()
        
        while not ws_closed and not ws_error:
            try:
                # 从队列中获取文本，超时0.1秒
                try:
                    text_chunk = text_queue.get(timeout=0.1)
                    
                    if text_chunk is None:  # 结束信号
                        # 如果缓冲区还有内容，先发送
                        if text_buffer.strip():
                            status = 0 if seq == 0 else 1
                            data_frame = wsParam.create_data_frame(text_buffer, status, seq)
                            d = {
                                "header": wsParam.CommonArgs,
                                "parameter": wsParam.BusinessArgs,
                                "payload": data_frame,
                            }
                            d["header"]["status"] = status
                            ws.send(json.dumps(d))
                            # 将打印改为写入日志文件
                            with open(send_log_file, 'a', encoding='utf-8') as f:
                                f.write(f"------>发送缓冲文本块 seq:{seq}, status:{status}, text:{text_buffer}...\n")
                            seq += 1
                        
                        # 发送结束帧
                        data_frame = wsParam.create_data_frame("。", 2, seq)  # 添加句号防止text为空
                        d = {
                            "header": wsParam.CommonArgs,
                            "parameter": wsParam.BusinessArgs,
                            "payload": data_frame,
                        }
                        d["header"]["status"] = 2  # 结束状态
                        ws.send(json.dumps(d))
                        print(f"------>发送结束帧 seq:{seq}")
                        break
                    
                    # 将文本添加到缓冲区
                    text_buffer += text_chunk
                    
                except queue.Empty:
                    # 队列为空，继续检查是否需要发送缓冲区内容
                    pass
                
                # 检查是否需要发送缓冲区内容（1秒间隔或缓冲区过大）
                current_time = time.time()
                should_send = False
                
                if text_buffer.strip():  # 缓冲区有内容
                    # 条件1：距离上次发送超过1秒
                    if current_time - last_send_time >= 1.0:
                        should_send = True
                    # 条件2：缓冲区内容过长（防止单次发送过多）
                    elif len(text_buffer) > 500:  # 超过500字符强制发送
                        should_send = True
                
                if should_send:
                    # 确定状态：第一帧为0（开始），后续为1（继续）
                    status = 0 if seq == 0 else 1
                    
                    # 创建数据帧
                    data_frame = wsParam.create_data_frame(text_buffer, status, seq)
                    d = {
                        "header": wsParam.CommonArgs,
                        "parameter": wsParam.BusinessArgs,
                        "payload": data_frame,
                    }
                    d["header"]["status"] = status
                    
                    ws.send(json.dumps(d))
                    # 将打印改为写入日志文件
                    with open(send_log_file, 'a', encoding='utf-8') as f:
                        f.write(f"------>发送累积文本块 seq:{seq}, status:{status}, 长度:{len(text_buffer)}, text:{text_buffer}...\n")
                    
                    # 重置缓冲区和时间
                    text_buffer = ""
                    last_send_time = current_time
                    seq += 1
                
            except Exception as e:
                print(f"发送文本时出错: {e}")
                ws_error = True
                break
    
    thread.start_new_thread(run, ())

# 为 voice.py 提供的接口函数
def stream_text_to_speech_init(appid, apisecret, apikey, filepath='./demo.raw'):
    """
    初始化流式文本转语音连接
    
    Args:
        appid (str): 应用ID
        apisecret (str): API密钥
        apikey (str): API密钥
        filepath (str): 输出音频文件路径
    
    Returns:
        bool: 如果成功建立连接返回True，否则返回False
    """
    global ws_closed, ws_error, text_queue, ws_instance, wsParam, current_filepath, audio_buffer, audio_writer_thread, audio_writing_finished
    
    # 重置全局状态
    ws_closed = False
    ws_error = False
    audio_writing_finished = False
    text_queue = queue.Queue()
    audio_buffer = queue.Queue()  # 重置音频缓冲区
    current_filepath = filepath
    
    try:
        wsParam = Ws_Param(APPID=appid, APISecret=apisecret, APIKey=apikey)
        websocket.enableTrace(False)
        requrl = 'wss://cbm01.cn-huabei-1.xf-yun.com/v1/private/mcd9m97e6'
        wsUrl = assemble_ws_auth_url(requrl, "GET", apikey, apisecret)
        print(f"生成的WebSocket URL: {wsUrl[:100]}...")
        
        # 启动音频写入线程
        audio_writer_thread = threading.Thread(target=audio_writer_worker, daemon=True)
        audio_writer_thread.start()
        print("音频写入线程已启动")
        
        ws_instance = websocket.WebSocketApp(wsUrl, on_message=on_message, on_error=on_error, on_close=on_close)
        ws_instance.on_open = on_open
        
        # 在新线程中启动WebSocket连接
        def run_websocket():
            ws_instance.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})
        
        ws_thread = threading.Thread(target=run_websocket, daemon=True)
        ws_thread.start()
        
        # 等待连接建立
        timeout = 10
        start_time = time.time()
        while ws_instance.sock is None and not ws_error and (time.time() - start_time) < timeout:
            time.sleep(0.1)
        
        if ws_instance.sock is not None:
            print("WebSocket连接已建立，可以开始发送文本流")
            return True
        else:
            print("WebSocket连接建立失败")
            return False
        
    except Exception as e:
        print(f"初始化TTS连接出错: {e}")
        return False

def stream_text_to_speech_send(text_chunk):
    """
    发送文本块到TTS服务
    
    Args:
        text_chunk (str): 文本块内容
    
    Returns:
        bool: 发送成功返回True，否则返回False
    """
    global text_queue, ws_closed, ws_error
    
    if ws_closed or ws_error:
        print("WebSocket连接已关闭或出错，无法发送文本")
        return False
    
    try:
        if text_chunk and text_chunk.strip():  # 只发送非空文本
            text_queue.put(text_chunk)
            return True
        return True  # 空文本也算成功
    except Exception as e:
        print(f"发送文本块出错: {e}")
        return False

def stream_text_to_speech_finish():
    """结束流式文本转语音"""
    global text_queue, ws_closed, ws_error, audio_writer_thread, audio_writing_finished
    
    try:
        # 发送结束信号
        text_queue.put(None)
        
        # 等待WebSocket处理完成
        timeout = 30
        start_time = time.time()
        while not ws_closed and not ws_error and (time.time() - start_time) < timeout:
            time.sleep(0.1)
        
        # 等待音频写入线程完成
        if audio_writer_thread and audio_writer_thread.is_alive():
            print("等待音频写入完成...")
            audio_writer_thread.join(timeout=10)  # 最多等待10秒
        
        # 检查音频写入是否完成
        if audio_writing_finished:
            print("音频写入已完成")
            return True
        else:
            print("音频写入可能未完全完成")
            return False
        
    except Exception as e:
        print(f"结束TTS转换出错: {e}")
        return False

# 修改第387行的函数定义，删除默认值
def text_to_speech(text, appid, apisecret, apikey, filepath='./demo.raw'):
    """
    一次性文本转语音函数（保持向后兼容）
    
    Args:
        text (str): 要转换的文本
        appid (str): 应用ID
        apisecret (str): API密钥
        apikey (str): API密钥
        filepath (str): 输出音频文件路径
    
    Returns:
        bool: 如果成功完成转换返回True，否则返回False
    """
    # 初始化连接
    if not stream_text_to_speech_init(appid, apisecret, apikey, filepath):
        return False
    
    # 发送文本
    if not stream_text_to_speech_send(text):
        return False
    
    # 结束转换
    return stream_text_to_speech_finish()

if __name__ == "__main__":
    # 删除硬编码的API密钥，改为从环境变量获取
    import os

    try:
    # load environment variables from .env file (requires `python-dotenv`)
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    appid=os.environ["appid"]
    apisecret=os.environ["apisecret"]
    apikey=os.environ["apikey"]
    
    if not all([appid, apisecret, apikey]):
        print("错误：请设置环境变量 APPID, APISECRET, APIKEY")
        exit(1)

    print("测试流式文本转语音...")
    
    # 初始化连接
    if stream_text_to_speech_init(appid, apisecret, apikey, './demo.raw'):
        # 模拟流式发送文本块
        text_chunks = ["这是第一段文本，", "这是第二段文本，", "这是最后一段文本。"]
        
        for chunk in text_chunks:
            if stream_text_to_speech_send(chunk):
                print(f"成功发送: {chunk}")
                time.sleep(0.5)  # 模拟流式间隔
            else:
                print(f"发送失败: {chunk}")
                break
        
        # 结束转换
        result = stream_text_to_speech_finish()
        print(f"流式转换结果: {result}")
    else:
        print("初始化失败")
