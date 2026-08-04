#!/usr/bin/env python3
"""诊断大模型 API Key 配置（Docker / 本地均可运行，无依赖新版 app 模块）"""

import os
import sys
from pathlib import Path
from typing import Optional

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Docker 下不加载镜像内占位符 .env
in_docker = os.getenv("DOCKER_CONTAINER", "").lower() in ("true", "1", "yes")
if not in_docker:
    try:
        from dotenv import load_dotenv
        load_dotenv(project_root / ".env", override=False)
    except ImportError:
        pass


def is_valid_api_key(api_key: Optional[str]) -> bool:
    if not api_key:
        return False
    api_key = api_key.strip()
    if len(api_key) <= 10:
        return False
    if api_key.startswith(("your_", "your-")):
        return False
    if api_key.endswith(("_here", "-here")):
        return False
    if "..." in api_key:
        return False
    return True


def normalize_llm_provider(provider_name: Optional[str]) -> str:
    if not provider_name:
        return "dashscope"
    aliases = {
        "qwen": "dashscope",
        "alibaba": "dashscope",
        "tongyi": "dashscope",
    }
    return aliases.get(provider_name.lower().strip(), provider_name.lower().strip())


def get_env_api_key_for_provider(provider_name: str) -> Optional[str]:
    normalized = normalize_llm_provider(provider_name)
    env_map = {
        "dashscope": ("DASHSCOPE_API_KEY", "QWEN_API_KEY"),
        "deepseek": ("DEEPSEEK_API_KEY",),
        "openai": ("OPENAI_API_KEY",),
        "google": ("GOOGLE_API_KEY",),
    }
    candidates = env_map.get(normalized, (f"{normalized.upper()}_API_KEY",))
    for var in candidates:
        val = os.getenv(var)
        if is_valid_api_key(val):
            return val.strip()
    return None


def resolve_llm_api_key(model_key, provider_key, provider: str) -> Optional[str]:
    if in_docker:
        env_key = get_env_api_key_for_provider(provider)
        if env_key:
            return env_key
    if is_valid_api_key(model_key):
        return model_key.strip()
    if is_valid_api_key(provider_key):
        return provider_key.strip()
    return get_env_api_key_for_provider(provider)


def mask(key: str) -> str:
    if not key or len(key) <= 12:
        return repr(key)
    return f"{key[:6]}...{key[-4:]}"


def main():
    print("=" * 60)
    print("LLM API Key diagnose")
    print("=" * 60)
    if in_docker:
        print("  mode: Docker (compose env > image .env)")

    for var in ("DASHSCOPE_API_KEY", "QWEN_API_KEY", "DEEPSEEK_API_KEY"):
        val = os.getenv(var)
        status = "OK" if is_valid_api_key(val) else ("INVALID" if val else "MISSING")
        print(f"  {var}: {status} {mask(val) if val else ''}")

    resolved = get_env_api_key_for_provider("qwen")
    print(f"\n  resolve qwen -> {mask(resolved) if resolved else 'NONE'}")
    print(f"  normalize qwen -> {normalize_llm_provider('qwen')}")

    try:
        from pymongo import MongoClient
        from app.core.config import settings

        client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client[settings.MONGO_DB]
        doc = db.system_configs.find_one({"is_active": True}, sort=[("version", -1)])
        if not doc:
            print("\n  WARN: no active system_configs in MongoDB")
        else:
            print(f"\n  system_configs version: {doc.get('version')}")
            for cfg in doc.get("llm_configs", []):
                if not cfg.get("enabled", True):
                    continue
                provider = cfg.get("provider", "")
                model = cfg.get("model_name", "")
                key = resolve_llm_api_key(cfg.get("api_key"), None, provider)
                db_ok = is_valid_api_key(cfg.get("api_key"))
                print(
                    f"  model {model} ({provider}): "
                    f"db={'OK' if db_ok else 'BAD'}, "
                    f"resolved={mask(key) if key else 'NONE'}, "
                    f"base={cfg.get('api_base', 'default')}"
                )

        for name in ("dashscope", "qwen", "deepseek"):
            pdoc = db.llm_providers.find_one({"name": name})
            if pdoc:
                pk = pdoc.get("api_key", "")
                print(f"  llm_providers.{name}: {'OK' if is_valid_api_key(pk) else 'BAD'} {mask(pk) if pk else ''}")
        client.close()
    except Exception as e:
        print(f"\n  WARN: MongoDB check failed: {e}")

    ds_key = get_env_api_key_for_provider("dashscope")
    if ds_key:
        try:
            import urllib.request

            req = urllib.request.Request(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/models",
                headers={"Authorization": f"Bearer {ds_key}"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                print(f"\n  DashScope probe: HTTP {resp.status} OK")
        except Exception as e:
            print(f"\n  DashScope probe FAILED: {e}")
    else:
        print("\n  skip DashScope probe (no valid key)")

    print("=" * 60)


if __name__ == "__main__":
    main()
