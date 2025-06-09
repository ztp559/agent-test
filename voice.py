import asyncio
import os
from voiceIO import play, record
from audioapi.s2t import recognize_speech
from audioapi.smarttts import stream_text_to_speech_init, stream_text_to_speech_send, stream_text_to_speech_finish
from Core import get_ai_response

# 加载环境变量
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 获取API配置
appid = os.environ["appid"]
apisecret = os.environ["apisecret"]
apikey = os.environ["apikey"]

# 配置常量
VOICE_FILE = "./origin_audio.raw"
AUDIO_FILE = "./demo.raw"
MIN_FILE_SIZE = 48000  # 最小文件大小(字节)
MAX_WAIT_TIME = 60    # 最大等待时间(秒)
SLEEP_INTERVAL = 0.1  # 发送间隔(秒)

async def async_voice_processing():
    """异步语音处理主函数"""
    
    # 1. 录音和语音识别
    print("开始录音...")
    record.record_audio(VOICE_FILE)
    userprompt = recognize_speech(VOICE_FILE)
    print(f"识别结果: {userprompt}")
    
    # 2. 获取AI响应流
    generator = get_ai_response(userprompt, 'Voice', stream=True)
    
    # 3. 清理旧文件
    if os.path.exists(AUDIO_FILE):
        try:
            os.remove(AUDIO_FILE)
            print(f"已删除旧文件: {AUDIO_FILE}")
        except Exception as e:
            print(f"删除文件失败: {e}")
            return
    
    # 4. 并行执行TTS和播放
    await asyncio.gather(
        process_tts_stream(generator),
        play_audio_async()
    )

async def process_tts_stream(generator):
    """处理TTS流数据"""
    tts_initialized = False
    
    async for chunk in generator:
        content = chunk.content.strip()
        if not content:  # 跳过空内容
            continue
            
        # 初始化TTS连接(仅一次)
        if not tts_initialized:
            loop = asyncio.get_event_loop()
            init_success = await loop.run_in_executor(
                None, stream_text_to_speech_init, appid, apisecret, apikey, AUDIO_FILE
            )
            if init_success:
                tts_initialized = True
                print("TTS连接已初始化")
            else:
                print("TTS初始化失败")
                return
        
        # 发送文本到TTS
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, stream_text_to_speech_send, content)
        await asyncio.sleep(SLEEP_INTERVAL)  # 控制发送频率
    
    # 完成TTS处理
    if tts_initialized:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, stream_text_to_speech_finish)
        print("TTS处理完成")

async def play_audio_async():
    """异步等待并播放音频"""
    wait_time = 0
    
    # 等待音频文件生成
    while wait_time < MAX_WAIT_TIME:
        if os.path.exists(AUDIO_FILE) and os.path.getsize(AUDIO_FILE) > MIN_FILE_SIZE:
            file_size = os.path.getsize(AUDIO_FILE)
            print(f"音频文件已生成({file_size} bytes)，开始播放...")
            
            # 异步播放音频
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, play.play_audio, AUDIO_FILE)
            return
        
        await asyncio.sleep(0.5)
        wait_time += 0.5
    
    print("等待超时，跳过播放")

if __name__ == "__main__":
    asyncio.run(async_voice_processing())