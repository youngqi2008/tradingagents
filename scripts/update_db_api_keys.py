#!/usr/bin/env python3
"""
更新数据库中的 API Key
从 .env 文件读取真实的 API Key，更新到 MongoDB（system_configs + llm_providers）
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 需要保护的环境变量（Compose 注入 > 镜像内 /app/.env 占位符）
_PROTECTED_ENV_VARS = (
    "DASHSCOPE_API_KEY",
    "QWEN_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "BAIDU_API_KEY",
    "OPENROUTER_API_KEY",
    "SILICONFLOW_API_KEY",
    "QIANFAN_API_KEY",
    "ANTHROPIC_API_KEY",
    "AI302_API_KEY",
    "TUSHARE_TOKEN",
    "FINNHUB_API_KEY",
)

# 先快照 Compose 已注入的环境变量，避免 load_dotenv 覆盖
_preserved_env = {
    name: value
    for name in _PROTECTED_ENV_VARS
    if (value := os.environ.get(name))
}

env_file = project_root / ".env"
in_docker = os.getenv("DOCKER_CONTAINER", "").lower() in ("true", "1", "yes")

if in_docker:
    print("🐳 Docker 模式：跳过镜像内 /app/.env，使用 Compose 注入的环境变量")
elif env_file.exists():
    load_dotenv(env_file, override=False)
    print(f"✅ 已加载 .env 文件（不覆盖已有环境变量）: {env_file}")
else:
    print(f"⚠️  .env 文件不存在: {env_file}，将仅使用当前环境变量")

# 恢复 Compose 注入的有效 Key（防止旧版 load_dotenv override=True 覆盖）
for name, value in _preserved_env.items():
    os.environ[name] = value


def _is_valid_key(key: Optional[str]) -> bool:
    from app.utils.api_key_utils import is_valid_api_key
    return is_valid_api_key(key)


def _load_env_api_keys() -> Dict[str, str]:
    """provider 名称 -> API Key（来自环境变量）"""
    env_map = {
        "dashscope": "DASHSCOPE_API_KEY",
        "qwen": "DASHSCOPE_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "openai": "OPENAI_API_KEY",
        "google": "GOOGLE_API_KEY",
        "baidu": "BAIDU_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "siliconflow": "SILICONFLOW_API_KEY",
        "qianfan": "QIANFAN_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "302ai": "AI302_API_KEY",
    }
    result: Dict[str, str] = {}
    for provider, env_var in env_map.items():
        val = os.getenv(env_var)
        if _is_valid_key(val):
            result[provider] = val.strip()
    return result


# 常见厂家的默认元数据（用于自动创建 llm_providers 记录）
_PROVIDER_BOOTSTRAP = {
    "dashscope": {
        "display_name": "阿里百炼",
        "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "website": "https://bailian.console.aliyun.com/",
    },
    "deepseek": {
        "display_name": "DeepSeek",
        "default_base_url": "https://api.deepseek.com",
        "website": "https://platform.deepseek.com/",
    },
    "siliconflow": {
        "display_name": "硅基流动",
        "default_base_url": "https://api.siliconflow.cn/v1",
        "website": "https://siliconflow.cn/",
    },
    "openai": {
        "display_name": "OpenAI",
        "default_base_url": "https://api.openai.com/v1",
        "website": "https://platform.openai.com/",
    },
    "google": {
        "display_name": "Google AI",
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta",
        "website": "https://ai.google.dev/",
    },
    "openrouter": {
        "display_name": "OpenRouter",
        "default_base_url": "https://openrouter.ai/api/v1",
        "website": "https://openrouter.ai/",
    },
}


async def update_llm_providers(db, api_keys: Dict[str, str]) -> int:
    """同步 llm_providers 集合（分析任务优先读取此处）"""
    providers_collection = db.llm_providers
    updated = 0

    print("\n🔄 更新 llm_providers 厂家配置:")
    provider_names = set(api_keys.keys()) | {"dashscope", "qwen", "deepseek", "openai", "google", "siliconflow"}

    for provider_name in sorted(provider_names):
        api_key = api_keys.get(provider_name) or api_keys.get(
            "dashscope" if provider_name == "qwen" else provider_name
        )
        if not api_key:
            continue

        existing = await providers_collection.find_one({"name": provider_name})
        if existing:
            old_key = existing.get("api_key", "")
            if old_key == api_key:
                print(f"  ⏭️  {provider_name}: 已是最新")
                continue
            await providers_collection.update_one(
                {"name": provider_name},
                {
                    "$set": {
                        "api_key": api_key,
                        "is_active": True,
                        "updated_at": datetime.utcnow(),
                    }
                },
            )
            print(f"  ✅ 更新 {provider_name}: {str(old_key)[:8]}... → {api_key[:8]}...")
            updated += 1
        elif provider_name in _PROVIDER_BOOTSTRAP:
            meta = _PROVIDER_BOOTSTRAP[provider_name]
            doc = {
                "name": provider_name,
                "display_name": meta["display_name"],
                "default_base_url": meta["default_base_url"],
                "website": meta.get("website"),
                "api_key": api_key,
                "is_active": True,
                "supported_features": ["chat"],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
            await providers_collection.insert_one(doc)
            print(f"  ✅ 创建 {provider_name} 厂家记录")
            updated += 1
        elif provider_name in ("dashscope", "deepseek", "openai", "google", "siliconflow", "openrouter"):
            print(f"  ⚠️  {provider_name}: 厂家记录不存在，请在后台「大模型配置」中初始化")

    return updated


async def update_system_configs(db, api_keys: Dict[str, str]) -> int:
    """同步 system_configs.llm_configs"""
    system_configs = db.system_configs
    config = await system_configs.find_one({"is_active": True}, sort=[("version", -1)])

    if not config:
        print("\n⚠️  数据库中没有激活的 system_configs，跳过 llm_configs 更新")
        return 0

    print(f"\n📊 当前 system_configs 版本: {config.get('version', 0)}")

    llm_configs = config.get("llm_configs", [])
    data_source_configs = config.get("data_source_configs", [])
    updated_count = 0

    print("\n🔄 更新 system_configs.llm_configs:")
    provider_aliases = {"qwen": "dashscope"}

    for llm_config in llm_configs:
        provider = llm_config.get("provider", "").lower()
        lookup = provider_aliases.get(provider, provider)
        env_key = api_keys.get(lookup) or api_keys.get(provider)
        old_key = llm_config.get("api_key", "")

        if env_key:
            if old_key != env_key or not _is_valid_key(old_key):
                llm_config["api_key"] = env_key
                llm_config["enabled"] = True
                print(f"  ✅ 更新 {provider}: → {env_key[:8]}...")
                updated_count += 1
            else:
                print(f"  ⏭️  {provider}: 已是最新")
        elif not _is_valid_key(old_key):
            llm_config["api_key"] = ""
            llm_config["enabled"] = False
            print(f"  🧹 清除 {provider} 的无效占位符 API Key")
            updated_count += 1

    print("\n🔄 更新数据源配置:")
    tushare_token = os.getenv("TUSHARE_TOKEN")
    if _is_valid_key(tushare_token):
        for ds_config in data_source_configs:
            if ds_config.get("type") == "tushare" and ds_config.get("api_key") != tushare_token:
                ds_config["api_key"] = tushare_token
                ds_config["enabled"] = True
                print("  ✅ 更新 TUSHARE_TOKEN")
                updated_count += 1
                break

    finnhub_key = os.getenv("FINNHUB_API_KEY")
    if _is_valid_key(finnhub_key):
        for ds_config in data_source_configs:
            if ds_config.get("type") == "finnhub" and ds_config.get("api_key") != finnhub_key:
                ds_config["api_key"] = finnhub_key
                ds_config["enabled"] = True
                print("  ✅ 更新 FINNHUB_API_KEY")
                updated_count += 1
                break

    if updated_count == 0:
        return 0

    new_version = config.get("version", 0) + 1
    result = await system_configs.update_one(
        {"_id": config["_id"]},
        {
            "$set": {
                "llm_configs": llm_configs,
                "data_source_configs": data_source_configs,
                "version": new_version,
            },
            "$currentDate": {"updated_at": True},
        },
    )
    if result.modified_count > 0:
        print(f"\n✅ system_configs 更新成功，新版本: {new_version}")
    return updated_count


async def update_api_keys():
    """更新数据库中的 API Key"""
    from app.core.database import get_mongo_db, init_db

    await init_db()
    db = get_mongo_db()

    print("\n" + "=" * 80)
    print("🔧 更新数据库中的 API Key")
    print("=" * 80)

    api_keys = _load_env_api_keys()

    print("\n📋 从环境变量读取的有效 API Key:")
    if in_docker:
        print("   （Docker 模式：使用 Compose 注入的环境变量，忽略镜像内 /app/.env 占位符）")
    dash = os.getenv("DASHSCOPE_API_KEY")
    if dash:
        print(f"   DASHSCOPE_API_KEY 探测: {'有效' if _is_valid_key(dash) else '无效/占位符'} (长度 {len(dash)})")
    for provider, key in sorted(api_keys.items()):
        if provider == "qwen":
            continue
        print(f"  ✅ {provider}: {key[:10]}... (长度: {len(key)})")
    if not api_keys:
        print("  ❌ 未找到任何有效 API Key，请先修正 .env")
        return

    providers_updated = await update_llm_providers(db, api_keys)
    configs_updated = await update_system_configs(db, api_keys)

    total = providers_updated + configs_updated
    if total > 0:
        print("\n💡 请重启后端以应用配置:")
        print("   docker compose -f docker-compose.hub.nginx.yml restart backend")
    else:
        print("\n⏭️  没有需要更新的配置（或 MongoDB 中已是正确 Key）")


async def main():
    try:
        await update_api_keys()
    except Exception as e:
        print(f"\n❌ 更新失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
