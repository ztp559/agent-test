import os

def get_prompt_template(template_name):
    """
    从本地.md文件读取模板内容
    
    Args:
        template_name (str): 模板名称（不包含.md扩展名）
        
    Returns:
        str: 对应的prompt模板字符串
    """
    try:
        # 构建文件路径
        file_path = f"{template_name}.md"
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            print(f"警告: 模板文件 {file_path} 不存在，使用默认模板")
            return get_default_template()
        
        # 读取文件内容
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read().strip()
            
        if not content:
            print(f"警告: 模板文件 {file_path} 为空，使用默认模板")
            return get_default_template()
            
        return content
        
    except Exception as e:
        print(f"读取模板文件时出错: {e}，使用默认模板")
        return get_default_template()

def get_default_template():
    """
    返回默认的助手模板
    
    Returns:
        str: 默认模板字符串
    """
    return "你是一个有用的AI助手，能够回答各种问题并提供帮助。请以友好、专业的态度为用户提供准确的信息和建议。"

def get_system_message(template_name):
    """
    获取系统消息格式的prompt模板
    
    Args:
        template_name (str): 模板名称
        
    Returns:
        tuple: ("system", prompt_template)
    """
    return ("system", get_prompt_template(template_name))

def list_available_templates():
    """
    列出当前目录下所有可用的.md模板文件
    
    Returns:
        list: 可用模板名称列表（不包含.md扩展名）
    """
    templates = []
    for file in os.listdir('.'):
        if file.endswith('.md'):
            templates.append(file[:-3])  # 移除.md扩展名
    return templates