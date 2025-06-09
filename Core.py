
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI核心模块
提供与AI模型交互的统一接口，支持流式和非流式输出
"""

import os
from typing import Union, Generator, Any
from langchain_modelscope import ModelScopeChatEndpoint
from template import get_system_message

# 尝试加载环境变量
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 缓存模型实例以提高性能
_model_cache = {}


def get_ai_response(userprompt: str, 
                   systemprompt: str = 'Claude', 
                   stream: bool = False) -> Union[str, Generator[str, None, None]]:
    """
    获取AI回复
    
    Args:
        userprompt (str): 用户输入的提示词
        systemprompt (str): 系统提示词类型，默认为'Claude'
        stream (bool): 是否使用流式输出，默认为False
    
    Returns:
        Union[str, Generator]: 非流式返回字符串，流式返回生成器
    
    Raises:
        ValueError: 当环境变量未设置时
        Exception: 当AI调用失败时
    """
    # 获取模型名称
    model_name = os.environ.get("modelname")
    if not model_name:
        raise ValueError("环境变量 'modelname' 未设置")
    
    # 格式化用户提示词
    formatted_prompt = f"'''{userprompt}'''"
    
    # 构建消息
    messages = [
        get_system_message(systemprompt),
        ("human", formatted_prompt),
    ]
    
    try:
        # 使用缓存的模型实例提高性能
        cache_key = f"{model_name}_{stream}"
        if cache_key not in _model_cache:
            _model_cache[cache_key] = ModelScopeChatEndpoint(model=model_name)
        
        llm = _model_cache[cache_key]
        
        if stream:
            # 流式输出
            return llm.astream(messages)
        else:
            # 非流式输出
            response = llm.invoke(messages)
            return response.content
            
    except Exception as e:
        print(f"AI调用失败: {e}")
        raise


def clear_model_cache() -> None:
    """
    清理模型缓存，释放内存
    """
    global _model_cache
    _model_cache.clear()
    print("模型缓存已清理")


if __name__ == "__main__":
    try:
        user_input = input("请输入你的问题: ")
        if not user_input.strip():
            print("输入不能为空")
            exit(1)
            
        print("AI回复:")
        ai_reply = get_ai_response(user_input)
        print(ai_reply)
        
    except KeyboardInterrupt:
        print("\n程序已退出")
    except Exception as e:
        print(f"程序执行失败: {e}")
        exit(1)