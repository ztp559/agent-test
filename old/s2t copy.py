import _thread as thread
import time
from time import mktime

import websocket

import base64
import datetime
import hashlib
import hmac
import json
import ssl
from datetime import datetime
from urllib.parse import urlencode
from wsgiref.handlers import format_date_time

# 添加父目录到 Python 路径
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 现在可以正常导入 voiceIO 模块
from voiceIO.record import record_audio

STATUS_FIRST_FRAME = 0  # 第一帧的标识
STATUS_CONTINUE_FRAME = 1  # 中间帧标识
STATUS_LAST_FRAME = 2  # 最后一帧的标识


class Ws_Param(object):
    # 初始化
    def __init__(self, APPID, APIKey, APISecret, AudioFile):
        self.APPID = APPID
        self.APIKey = APIKey
        self.APISecret = APISecret
        self.AudioFile = AudioFile
        self.iat_params = {
            "domain": "slm", "language": "zh_cn", "accent": "mandarin","dwa":"wpgs", "result":
                {
                    "encoding": "utf8",
                    "compress": "raw",
                    "format": "plain"
                }
        }

    # 生成url
    def create_url(self):
        url = 'ws://iat.xf-yun.com/v1'
        # 生成RFC1123格式的时间戳
        now = datetime.now()
        date = format_date_time(mktime(now.timetuple()))

        # 拼接字符串
        signature_origin = "host: " + "iat.xf-yun.com" + "\n"
        signature_origin += "date: " + date + "\n"
        signature_origin += "GET " + "/v1 " + "HTTP/1.1"
        # 进行hmac-sha256进行加密
        signature_sha = hmac.new(self.APISecret.encode('utf-8'), signature_origin.encode('utf-8'),
                                 digestmod=hashlib.sha256).digest()
        signature_sha = base64.b64encode(signature_sha).decode(encoding='utf-8')

        authorization_origin = "api_key=\"%s\", algorithm=\"%s\", headers=\"%s\", signature=\"%s\"" % (
            self.APIKey, "hmac-sha256", "host date request-line", signature_sha)
        authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode(encoding='utf-8')
        # 将请求的鉴权参数组合为字典
        v = {
            "authorization": authorization,
            "date": date,
            "host": "iat.xf-yun.com"
        }
        # 拼接鉴权参数，生成url
        url = url + '?' + urlencode(v)
        return url


# 语音识别类
class SpeechRecognizer:
    def __init__(self, appid, api_key, api_secret):
        self.appid = appid
        self.api_key = api_key
        self.api_secret = api_secret
        self.final_result = ""
        self.latest_result = ""
        self.recognition_complete = False
        self.error_occurred = False
        self.error_message = ""

    def on_message(self, ws, message):
        message = json.loads(message)
        code = message["header"]["code"]
        status = message["header"]["status"]
        if code != 0:
            self.error_occurred = True
            self.error_message = f"请求错误：{code}"
            ws.close()
        else:
            payload = message.get("payload")
            if payload:
                text = payload["result"]["text"]
                text = json.loads(str(base64.b64decode(text), "utf8"))
                text_ws = text['ws']
                result = ''
                for i in text_ws:
                    for j in i["cw"]:
                        w = j["w"]
                        result += w
                # 只有当新结果比之前的结果更长时才更新
                if len(result) > len(self.latest_result):
                    self.latest_result = result
            if status == 2:
                self.final_result = self.latest_result
                self.recognition_complete = True
                ws.close()

    def on_error(self, ws, error):
        self.error_occurred = True
        self.error_message = f"WebSocket错误: {error}"

    def on_close(self, ws, close_status_code, close_msg):
        pass

    def on_open(self, ws, audio_file):
        def run(*args):
            frameSize = 1280  # 每一帧的音频大小
            intervel = 0.04  # 发送音频间隔(单位:s)
            status = STATUS_FIRST_FRAME  # 音频的状态信息，标识音频是第一帧，还是中间帧、最后一帧

            wsParam = Ws_Param(self.appid, self.api_key, self.api_secret, audio_file)

            with open(audio_file, "rb") as fp:
                while True:
                    buf = fp.read(frameSize)
                    audio = str(base64.b64encode(buf), 'utf-8')

                    # 文件结束
                    if not buf:
                        status = STATUS_LAST_FRAME
                    # 第一帧处理
                    if status == STATUS_FIRST_FRAME:
                        d = {"header":
                            {
                                "status": 0,
                                "app_id": wsParam.APPID
                            },
                            "parameter": {
                                "iat": wsParam.iat_params
                            },
                            "payload": {
                                "audio":
                                    {
                                        "audio": audio, "sample_rate": 16000, "encoding": "raw"
                                    }
                            }}
                        d = json.dumps(d)
                        ws.send(d)
                        status = STATUS_CONTINUE_FRAME
                    # 中间帧处理
                    elif status == STATUS_CONTINUE_FRAME:
                        d = {"header": {"status": 1,
                                        "app_id": wsParam.APPID},
                             "parameter": {
                                 "iat": wsParam.iat_params
                             },
                             "payload": {
                                 "audio":
                                     {
                                         "audio": audio, "sample_rate": 16000, "encoding": "raw"
                                     }}}
                        ws.send(json.dumps(d))
                    # 最后一帧处理
                    elif status == STATUS_LAST_FRAME:
                        d = {"header": {"status": 2,
                                        "app_id": wsParam.APPID
                                        },
                             "parameter": {
                                 "iat": wsParam.iat_params
                             },
                             "payload": {
                                 "audio":
                                     {
                                         "audio": audio, "sample_rate": 16000, "encoding": "raw"
                                     }}}
                        ws.send(json.dumps(d))
                        break

                    # 模拟音频采样间隔
                    time.sleep(intervel)

        thread.start_new_thread(run, ())

    def recognize_audio(self, audio_file, timeout=30):
        """
        识别音频文件并返回最终结果
        
        Args:
            audio_file (str): 音频文件路径
            timeout (int): 超时时间（秒）
            
        Returns:
            str: 识别结果，如果出错返回错误信息
        """
        # 重置状态
        self.final_result = ""
        self.latest_result = ""
        self.recognition_complete = False
        self.error_occurred = False
        self.error_message = ""
        
        # 创建WebSocket参数
        wsParam = Ws_Param(self.appid, self.api_key, self.api_secret, audio_file)
        websocket.enableTrace(False)
        wsUrl = wsParam.create_url()
        
        # 创建WebSocket连接
        ws = websocket.WebSocketApp(wsUrl, 
                                   on_message=self.on_message, 
                                   on_error=self.on_error, 
                                   on_close=self.on_close)
        ws.on_open = lambda ws: self.on_open(ws, audio_file)
        
        # 启动WebSocket连接（非阻塞）
        import threading
        ws_thread = threading.Thread(target=lambda: ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}))
        ws_thread.daemon = True
        ws_thread.start()
        
        # 等待识别完成或超时
        start_time = time.time()
        while not self.recognition_complete and not self.error_occurred:
            if time.time() - start_time > timeout:
                ws.close()
                return "识别超时"
            time.sleep(0.1)
        
        if self.error_occurred:
            return self.error_message
        
        return self.final_result


# 便捷函数
def recognize_speech(audio_file, appid='15a90977', api_secret='MmVjMzA4NDExYTgxMzAzYjUxYzFjMDM5', 
                    api_key='64acce84dee079661249e08083636471', timeout=30):
    """
    语音识别便捷函数
    
    Args:
        audio_file (str): 音频文件路径
        appid (str): 应用ID
        api_secret (str): API密钥
        api_key (str): API Key
        timeout (int): 超时时间（秒）
        
    Returns:
        str: 识别结果
    """
    recognizer = SpeechRecognizer(appid, api_key, api_secret)
    return recognizer.recognize_audio(audio_file, timeout)


if __name__ == "__main__":
    # 测试代码
    audio_file = r'/home/duduzhang/agent/origin_audio.raw'
    record_audio(audio_file)
    result = recognize_speech(audio_file)
    print(f"识别结果: {result}")
