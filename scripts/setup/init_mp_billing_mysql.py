#!/usr/bin/env python3
"""初始化 MySQL 用户/计费表（可选，应用启动时也会 auto create_all）"""

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


async def main() -> None:
    from app.core.mysql_db import init_mysql, close_mysql
    from app.services.membership_service import membership_service

    await init_mysql()
    await membership_service.init_default_levels()
    await close_mysql()
    print("✅ MySQL 用户/计费模块初始化完成")


if __name__ == "__main__":
    asyncio.run(main())
