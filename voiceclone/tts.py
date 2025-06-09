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


STATUS_FIRST_FRAME = 0  # 第一帧的标识
STATUS_CONTINUE_FRAME = 1  # 中间帧标识
STATUS_LAST_FRAME = 2  # 最后一帧的标识


class Ws_Param(object):
    # 初始化
    def __init__(self, APPID, APIKey, APISecret, Text,res_id):
        self.APPID = APPID
        self.APIKey = APIKey
        self.APISecret = APISecret
        self.Text = Text

        # 公共参数(common)
        # 在这里通过res_id 来设置通过哪个音库合成
        self.CommonArgs = {"app_id": self.APPID,"res_id":res_id,"status":2}
        # 业务参数(business)，更多个性化参数可在官网查看
        self.BusinessArgs = {
        "tts": {
            "rhy":1,
            "vcn": "x5_clone",  # 固定值
            "volume": 50,    #设置音量大小
            "rhy": 0,
            "pybuffer": 1,
            "speed": 50,    #设置合成语速，值越大，语速越快
            "pitch": 50,    #设置振幅高低，可通过该参数调整效果
            "bgs": 0,
            "reg": 0,
            "rdn": 0,
            "audio": {
                "encoding": "lame",  #合成音频格式
                "sample_rate": 16000,  #合成音频采样率
                "channels": 1,
                "bit_depth": 16,
                "frame_size": 0
            },
            "pybuf": {
                "encoding": "utf8",
                "compress": "raw",
                "format": "plain"
            }
        }
    }
        # self.Data = {"status": 2, "text": str(base64.b64encode(self.Text.encode('utf-8')), "UTF8")}
        self.Data = {
        "text": {
            "encoding": "utf8",
            "compress": "raw",
            "format": "plain",
            "status": 2,
            "seq": 0,
            "text": str(base64.b64encode(self.Text.encode('utf-8')), "UTF8")   # 待合成文本base64格式
        }
        }


class AssembleHeaderException(Exception):
    def __init__(self, msg):
        self.message = msg


class Url:
    def __init__(this, host, path, schema):
        this.host = host
        this.path = path
        this.schema = schema
        pass


# calculate sha256 and encode to base64
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


# build websocket auth request url
def assemble_ws_auth_url(requset_url, method="GET", api_key="", api_secret=""):
    u = parse_url(requset_url)
    host = u.host
    path = u.path
    now = datetime.now()
    date = format_date_time(mktime(now.timetuple()))
    print(date)
    # date = "Thu, 12 Dec 2019 01:57:27 GMT"
    signature_origin = "host: {}\ndate: {}\n{} {} HTTP/1.1".format(host, date, method, path)
    # print(signature_origin)
    signature_sha = hmac.new(api_secret.encode('utf-8'), signature_origin.encode('utf-8'),
                             digestmod=hashlib.sha256).digest()
    signature_sha = base64.b64encode(signature_sha).decode(encoding='utf-8')
    authorization_origin = "api_key=\"%s\", algorithm=\"%s\", headers=\"%s\", signature=\"%s\"" % (
        api_key, "hmac-sha256", "host date request-line", signature_sha)
    authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode(encoding='utf-8')
    # print(authorization_origin)
    values = {
        "host": host,
        "date": date,
        "authorization": authorization
    }

    return requset_url + "?" + urlencode(values)

# 全局变量用于存储当前的输出文件路径
current_output_file = './demo.mp3'

def on_message(ws, message):
    try:
        print(message)
        # data = json.dumps(message)
        message = json.loads(message)
        # print(message)
        # message =json.loads(message)
        code = message["header"]["code"]
        sid = message["header"]["sid"]
        if("payload" in message):
            audio = message["payload"]["audio"]['audio']
            audio = base64.b64decode(audio)
            status = message["payload"]['audio']["status"]
            print(message)
            if status == 2:
                print("ws is closed")
                ws.close()
            if code != 0:
                errMsg = message["message"]
                print("sid:%s call error:%s code is:%s" % (sid, errMsg, code))
            else:

                with open(current_output_file, 'ab') as f:    # 这里文件后缀名，需要和业务参数audio.encoding 对应
                    f.write(audio)

    except Exception as e:
        print("receive msg,but parse exception:", e)



# 收到websocket错误的处理
def on_error(ws, error):
    # return 0
    print("### error:", error)




# 收到websocket关闭的处理
def on_close(ws,ts,end):
    return 0
    # print("### closed ###")


# 收到websocket连接建立的处理
def on_open(ws):
    def run(*args):
        d = {"header": wsParam.CommonArgs,
             "parameter": wsParam.BusinessArgs,
             "payload": wsParam.Data,
             }
        d = json.dumps(d)
        print("------>开始发送文本数据")
        ws.send(d)
        if os.path.exists(current_output_file):
            os.remove(current_output_file)

    thread.start_new_thread(run, ())


def text_to_speech(text, res_id, appid, apisecret, apikey, output_file='./demo.mp3', play_audio=True):
    """
    文本转语音函数
    
    参数:
    text: 要转换的文本
    res_id: 音库ID
    appid: 应用ID
    apisecret: API密钥
    apikey: API密钥
    output_file: 输出音频文件路径，默认为'./demo.mp3'
    play_audio: 是否播放生成的音频，默认为True
    
    返回:
    bool: 成功返回True，失败返回False
    """
    global wsParam, current_output_file
    
    try:
        # 设置当前输出文件路径
        current_output_file = output_file
        
        wsParam = Ws_Param(APPID=appid, APISecret=apisecret,
                           APIKey=apikey,
                           Text=text, res_id=res_id)
        websocket.enableTrace(False)
        requrl = 'wss://cn-huabei-1.xf-yun.com/v1/private/voice_clone'
        wsUrl = assemble_ws_auth_url(requrl, "GET", apikey, apisecret)
        ws = websocket.WebSocketApp(wsUrl, on_message=on_message, on_error=on_error, on_close=on_close)
        ws.on_open = on_open
        ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})
        
        # 检查文件是否生成成功
        if os.path.exists(output_file):
            print(f"音频文件已生成: {output_file}")
            if play_audio:
                os.system(f"mpg123 {output_file}")
            return True
        else:
            print("音频文件生成失败")
            return False
            
    except Exception as e:
        print(f"文本转语音过程中发生错误: {e}")
        return False


if __name__ == "__main__":
    res_id ='73e4607_ttsclone-15a90977-joyqr'  #这里填写训练完成后，得到的音库id
    # 测试时候在此处正确填写相关信息即可运行
    appid = '15a90977' #在控制台获取appid
    apisecret = 'MmVjMzA4NDExYTgxMzAzYjUxYzFjMDM5'#在控制台获取secret
    apikey = '64acce84dee079661249e08083636471'#在控制台获取key
    
    text = "尊贵的杜宇晨小姐和张峻泽小朋友，我是张天鹏的语音助理，我可以为您提供帮助。"
    
    # 调用新的函数
    success = text_to_speech(text, res_id, appid, apisecret, apikey)
    if success:
        print("语音合成完成")
    else:
        print("语音合成失败")
