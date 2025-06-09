import json
import time
import requests
import hashlib
import os
from requests_toolbelt.multipart.encoder import MultipartEncoder

# 获取鉴权token
def getAuthorization(appId, apikey,timeStamp,data):
    # timeStamp = int(time.time() * 1000)
    # data = '{"base":{"appid":"' + appId + '","version":"v1","timestamp":"' + str(timeStamp) + '"},"model":"remote"}'
    body = json.dumps(data)
    keySign = hashlib.md5((apikey + str(timeStamp)).encode('utf-8')).hexdigest()
    print(body)
    sign = hashlib.md5((keySign + body).encode("utf-8")).hexdigest()
    return sign
#获取鉴权token
def getToken(appid,apikey):
    #构建请求头headers
    timeStamp = int(time.time() * 1000)
    body = {"base":{"appid": appid ,"version":"v1","timestamp": str(timeStamp)},"model":"remote"}
    headers = {}
    headers['Authorization'] = getAuthorization(appid,apikey,timeStamp,body)
    headers['Content-Type'] = 'application/json'
    print("body------>",body)
    print("headers----->",headers)
    response = requests.post(url='http://avatar-hci.xfyousheng.com/aiauth/v1/token', data= json.dumps(body),headers= headers).text
    resp = json.loads(response)
    print("resp---->",resp)
    if ('000000' == resp['retcode']):
        return resp['accesstoken']


class VoiceTrain(object):
    def __init__(self,appid,apikey):
        # self.sign = ''
        self.appid = appid
        self.apikey = apikey
        self.token = getToken(appid,apikey)
        self.time = int(time.time()* 1000)
        self.taskId = ''

    def getSign(self,body):
        keySign = hashlib.md5((str(body)).encode('utf-8')).hexdigest()
        sign = hashlib.md5((self.apikey+ str(self.time) + keySign).encode("utf-8")).hexdigest()
        return sign

    def getheader(self,sign):
        return {"X-Sign":sign,"X-Token":self.token,"X-AppId":self.appid,"X-Time":str(self.time)}

    #支持获取训练文本列表
    def getText(self):
        textid = 5001  #通用的训练文本集
        body = {"textId":textid}
        sign = self.getSign(body)
        headers =self.getheader(sign)

        response = requests.post(url ='http://opentrain.xfyousheng.com/voice_train/task/traintext',json= body,headers=headers).json()
        print(response)
        
        # 将response内容保存到getText.json文件
        import os
        # 获取当前脚本所在目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        json_file_path = os.path.join(current_dir, 'getText.json')
        
        # 保存response到JSON文件
        with open(json_file_path, 'w', encoding='utf-8') as f:
            json.dump(response, f, ensure_ascii=False, indent=2)
        
        print(f"Response已保存到: {json_file_path}")
        
        print("请使用以下官方文本录音，然后进行训练：")
        textlist= response['data']['textSegs']
        for line in textlist:
            print(line['segId'])
            print(line['segText'])

    #创建训练任务
    def createTask(self):
        body={
            "taskName":"test23",  #任务名称，可自定义
            "sex" :1 ,  # 训练音色性别   1：男     2 ：女
            "resourceType":12,
            "resourceName" :"创建音库test1",  #音库名称，可自定义
            "language":"cn",   # 不传language参数，默认中文；英：en、日：jp、韩：ko、俄：ru
            # "callbackUrl":"https://XXXX/../"   #任务结果回调地址
        }
        sign = self.getSign(body)
        headers = self.getheader(sign)
        response = requests.post(url ='http://opentrain.xfyousheng.com/voice_train/task/add',json= body,headers=headers).text
        print(response)
        resp = json.loads(response)
        print("创建任务：",resp)
        return resp['data']

    #添加音频到训练任务（上传音频url）
    ##音频要求：
    # 1、音频格式限制wav、mp3、m4a、pcm，推荐使用无压缩wav格式
    # 2、单通道，采样率24k及以上，位深度16bit，时长无严格限制，音频大小限制3M。音频大小限制3M
    def addAudio(self,audiourl,textId,textSegId):
        self.taskId =self.createTask()
        body ={
            "taskId":self.taskId,
            "audioUrl": audiourl,  #wav格式音频的存储对象地址，需保证地址可直接下载
            "textId": textId,   #通用训练文本集
            "textSegId": textSegId     #这里demo 演示用固定文本训练，应用层可以让用户从 getText返回的列表中选择
        }
        sign = self.getSign(body)
        headers = self.getheader(sign)
        response = requests.post(url='http://opentrain.xfyousheng.com/voice_train/audio/v1/add', json=body, headers=headers).text
        print(response)

    # 添加音频到训练任务（上传本地音频文件）
    ##音频要求：
    # 1、音频格式限制wav、mp3、m4a、pcm，推荐使用无压缩wav格式
    # 2、单通道，采样率24k及以上，位深度16bit，时长无严格限制，音频大小限制3M。音频大小限制3M
    def addAudiofromPC(self,  textId, textSegId,path):
        url = 'http://opentrain.xfyousheng.com/voice_train/task/submitWithAudio'
        self.taskId = self.createTask()
        # body = {
        #     "taskId": self.taskId,
        #     "audioUrl": audiourl,  # wav格式音频的存储对象地址，需保证地址可直接下载
        #     "textId": textId,  # 通用训练文本集
        #     "textSegId": textSegId  # 这里demo 演示用固定文本训练，应用层可以让用户从 getText返回的列表中选择
        # }
        # 构造body体
        formData = MultipartEncoder(
            fields={
                "file": (path, open(path, 'rb'), 'audio/wav'),  # 如果需要上传本地音频文件，可以将文件路径通过path 传入
                "taskId": str(self.taskId),
                "textId": str(textId),  # 通用训练文本集
                "textSegId": str(textSegId)  # 这里demo 演示用固定文本训练，应用层可以让用户从 getText返回的列表中选择
            }
        )
        print(formData)

        sign = self.getSign(formData)
        headers = self.getheader(sign)
        headers['Content-Type'] = formData.content_type
        response = requests.post(url=url, data= formData,headers=headers).text
        print(response)


    def submitTask(self):
        body ={"taskId" :self.taskId}
        sign = self.getSign(body)
        headers = self.getheader(sign)
        response = requests.post(url='http://opentrain.xfyousheng.com/voice_train/task/submit', json=body, headers=headers).text
        print(response)

    def getProcess(self):
        body = {"taskId": self.taskId}
        sign = self.getSign(body)
        headers = self.getheader(sign)
        response = requests.post(url='http://opentrain.xfyousheng.com/voice_train/task/result', json=body, headers=headers).text
        # resp = json.loads(response)
        return response




def train_voice_model(appid, apikey, segid=None, audio_path=None):
    """
    训练语音模型并返回res_id
    
    Args:
        appid: 应用ID
        apikey: API密钥
        segid: 文本编号（可选，如果不提供会提示用户输入）
        audio_path: 音频文件路径（可选，默认为'./origin_audio.wav'）
    
    Returns:
        str: 成功时返回res_id，失败时返回None
    """
    voiceTrain = VoiceTrain(appid, apikey)
    
    # 获取训练文本列表
    voiceTrain.getText()
    
    # 如果没有提供segid，则提示用户输入
    if segid is None:
        segid = input("请使用官方文本录音，然后进行训练，输入文本编号：")
    
    # 如果没有提供音频路径，使用默认路径并录音
    if audio_path is None:
        audio_path = './origin_audio.wav'
        os.system('rec ./origin_audio.wav')
    
    # 添加音频到训练任务中
    voiceTrain.addAudiofromPC(textId=5001, textSegId=segid, path=audio_path)
    
    # 提交训练任务
    voiceTrain.submitTask()
    
    # 轮询训练结果
    while True:
        response = voiceTrain.getProcess()
        resp = json.loads(response)
        status = resp['data']['trainStatus']
        
        if status == -1:
            print("还在训练中，请等待......")
            time.sleep(5)  # 等待5秒后再次检查
        elif status == 1:
            print("训练成功，请用该音库开始进行语音合成：")
            res_id = resp['data']['assetId']
            print("音库id(res_id)：", res_id)
            return res_id  # 返回res_id
        elif status == 0:
            print("训练失败，训练时上传的音频必须要使用官方提供的文本录音，文本列表见：voiceTrain.getText() 方法执行结果")
            print(voiceTrain.taskId)
            return None  # 训练失败返回None
        else:
            print(f"未知的voiceTrain.submitTask状态: {status}")
            return None

if __name__ == '__main__':
    appid = '15a90977'  # 在控制台获取
    apikey = '64acce84dee079661249e08083636471'  # 在控制台获取
    
    # 调用训练函数
    result = train_voice_model(appid, apikey)
    
    if result:
        print(f"训练完成，音库ID: {result}")
    else:
        print("训练失败")