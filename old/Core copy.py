import getpass
import os
from langchain_modelscope import ModelScopeChatEndpoint
#from langchain_community.chat_models.tongyi import ChatTongyi
from template import get_system_message

try:
    # load environment variables from .env file (requires `python-dotenv`)
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

def get_ai_response(userprompt: str, systemprompt='Claude', stream: bool = False) -> str:
    """
    获取AI回复
    
    Args:
        systemprompt (str): 系统提示词类型，默认为'Claude'
        userprompt (str): 用户输入的提示词
        stream (bool): 是否使用流式输出，默认为False
    
    Returns:
        str: AI的回复内容
    """
    load_dotenv()
    
    # 格式化用户提示词
    formatted_prompt = userprompt=f"'''{userprompt}'''"
    
    # 使用模板系统创建消息
    messages = [
        get_system_message(systemprompt),  # 修复：明确指定为system消息
        ("human", formatted_prompt),
    ]
    
    # 初始化模型并获取回复
    model=os.environ["modelname"]
    
    if stream:
        llm = ModelScopeChatEndpoint(model=model)  # 使用关键字参数
        generator = llm.astream(messages)
        return generator
    else:
        # 非流式输出
        llm = ModelScopeChatEndpoint(model=model)  # 使用关键字参数
        response = llm.invoke(messages)
        return response.content

if __name__ == "__main__":
    # 示例用法
    user_input = input("请输入你的问题: ")
    ai_reply = get_ai_response(user_input)
    print("AI回复:")
    print(ai_reply)