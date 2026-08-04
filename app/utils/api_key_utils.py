"""
API Key 处理工具函数

提供统一的 API Key 验证、缩略、环境变量读取等功能
"""

import os
from typing import Optional


def is_valid_api_key(api_key: Optional[str]) -> bool:
    """
    判断 API Key 是否有效
    
    有效的 API Key 必须满足：
    1. 不能为空
    2. 长度必须 > 10
    3. 不能是占位符（前缀：your_, your-）
    4. 不能是占位符（后缀：_here, -here）
    5. 不能是截断的密钥（包含 '...'）
    
    Args:
        api_key: 要验证的 API Key
        
    Returns:
        bool: 是否有效
    """
    if not api_key:
        return False
    
    api_key = api_key.strip()
    
    # 1. 不能为空
    if not api_key:
        return False
    
    # 2. 长度必须 > 10
    if len(api_key) <= 10:
        return False
    
    # 3. 不能是占位符（前缀）
    if api_key.startswith('your_') or api_key.startswith('your-'):
        return False
    
    # 4. 不能是占位符（后缀）
    if api_key.endswith('_here') or api_key.endswith('-here'):
        return False
    
    # 5. 不能是截断的密钥（包含 '...'）
    if '...' in api_key:
        return False
    
    return True


def truncate_api_key(api_key: Optional[str]) -> Optional[str]:
    """
    缩略 API Key，显示前6位和后6位
    
    示例：
        输入：'d1el869r01qghj41hahgd1el869r01qghj41hai0'
        输出：'d1el86...j41hai0'
    
    Args:
        api_key: 要缩略的 API Key
        
    Returns:
        str: 缩略后的 API Key，如果输入为空或长度 <= 12 则返回原值
    """
    if not api_key or len(api_key) <= 12:
        return api_key
    
    return f"{api_key[:6]}...{api_key[-6:]}"


def normalize_llm_provider(provider_name: Optional[str]) -> str:
    """将数据库/配置中的 provider 别名统一为引擎识别的厂家名"""
    if not provider_name:
        return "dashscope"
    aliases = {
        "qwen": "dashscope",
        "alibaba": "dashscope",
        "tongyi": "dashscope",
        "通义千问": "dashscope",
        "阿里百炼": "dashscope",
    }
    return aliases.get(provider_name.lower().strip(), provider_name.lower().strip())


def resolve_llm_api_key(
    model_api_key: Optional[str],
    provider_api_key: Optional[str],
    provider: str,
) -> Optional[str]:
    """解析 LLM API Key：Docker 环境变量 > 模型配置 > 厂家配置 > 环境变量（跳过占位符）"""
    normalized = normalize_llm_provider(provider)
    env_key = get_env_api_key_for_provider(normalized)

    # Docker 部署时 Compose 注入的 Key 优先，避免 MongoDB 中过期/错误的 Key 覆盖真实配置
    if os.getenv("DOCKER_CONTAINER", "").lower() in ("true", "1", "yes"):
        if env_key:
            return env_key

    if is_valid_api_key(model_api_key):
        return model_api_key.strip()
    if is_valid_api_key(provider_api_key):
        return provider_api_key.strip()
    return env_key


def get_env_api_key_for_provider(provider_name: str) -> Optional[str]:
    """
    从环境变量获取大模型厂家的 API Key
    
    环境变量名格式：{PROVIDER_NAME}_API_KEY
    """
    provider_aliases = {
        "qwen": "dashscope",
        "alibaba": "dashscope",
        "tongyi": "dashscope",
        "通义千问": "dashscope",
        "阿里百炼": "dashscope",
    }
    normalized = provider_aliases.get((provider_name or "").lower(), (provider_name or "").lower())

    env_key_map = {
        "dashscope": "DASHSCOPE_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "openai": "OPENAI_API_KEY",
        "google": "GOOGLE_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "siliconflow": "SILICONFLOW_API_KEY",
        "qianfan": "QIANFAN_API_KEY",
        "302ai": "AI302_API_KEY",
        "zhipu": "ZHIPU_API_KEY",
    }

    env_key_name = env_key_map.get(normalized) or f"{normalized.upper()}_API_KEY"
    env_key = os.getenv(env_key_name)
    
    if env_key and is_valid_api_key(env_key):
        return env_key
    
    return None


def get_env_api_key_for_datasource(ds_type: str) -> Optional[str]:
    """
    从环境变量获取数据源的 API Key
    
    数据源类型到环境变量名的映射：
    - tushare → TUSHARE_TOKEN
    - finnhub → FINNHUB_API_KEY
    - polygon → POLYGON_API_KEY
    - iex → IEX_API_KEY
    - quandl → QUANDL_API_KEY
    - alphavantage → ALPHAVANTAGE_API_KEY
    
    Args:
        ds_type: 数据源类型（如 'tushare', 'finnhub'）
        
    Returns:
        str: 环境变量中的 API Key，如果不存在或无效则返回 None
    """
    # 数据源类型到环境变量名的映射
    env_key_map = {
        "tushare": "TUSHARE_TOKEN",
        "finnhub": "FINNHUB_API_KEY",
        "polygon": "POLYGON_API_KEY",
        "iex": "IEX_API_KEY",
        "quandl": "QUANDL_API_KEY",
        "alphavantage": "ALPHAVANTAGE_API_KEY",
    }
    
    env_key_name = env_key_map.get(ds_type.lower())
    if not env_key_name:
        return None
    
    env_key = os.getenv(env_key_name)
    
    if env_key and is_valid_api_key(env_key):
        return env_key
    
    return None


def should_skip_api_key_update(api_key: Optional[str]) -> bool:
    """
    判断是否应该跳过 API Key 的更新
    
    以下情况应该跳过更新（保留原值）：
    1. API Key 是截断的密钥（包含 '...'）
    2. API Key 是占位符（your_*, your-*）
    
    Args:
        api_key: 要检查的 API Key
        
    Returns:
        bool: 是否应该跳过更新
    """
    if not api_key:
        return False
    
    api_key = api_key.strip()
    
    # 1. 截断的密钥（包含 '...'）
    if '...' in api_key:
        return True
    
    # 2. 占位符
    if api_key.startswith('your_') or api_key.startswith('your-'):
        return True
    
    return False

