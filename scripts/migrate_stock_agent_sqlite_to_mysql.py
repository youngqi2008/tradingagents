#!/usr/bin/env python3
"""将问股 Agent 旧 SQLite 数据一次性迁移到 MySQL。

用法（项目根目录）:
  python scripts/migrate_stock_agent_sqlite_to_mysql.py
  python scripts/migrate_stock_agent_sqlite_to_mysql.py --sqlite-path ./data/stock_analysis.db
  python scripts/migrate_stock_agent_sqlite_to_mysql.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("migrate_sa_sqlite")

TABLES = [
    "stock_daily",
    "news_intel",
    "analysis_history",
    "backtest_results",
    "backtest_summaries",
    "conversation_messages",
    "llm_usage",
]


def migrate(sqlite_path: Path, dry_run: bool) -> None:
    if not sqlite_path.exists():
        logger.warning("SQLite 文件不存在，跳过迁移: %s", sqlite_path)
        return

    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.orm import sessionmaker

    from app.core.config import settings
    from app.core.mysql_db import get_sync_mysql_url
    from app.stock_agent.dsa_storage import Base

    sqlite_url = f"sqlite:///{sqlite_path.resolve()}"
    mysql_url = get_sync_mysql_url()

    src_engine = create_engine(sqlite_url)
    dst_engine = create_engine(
        mysql_url,
        pool_pre_ping=True,
        pool_size=settings.MYSQL_POOL_SIZE,
        max_overflow=settings.MYSQL_MAX_OVERFLOW,
    )

    Base.metadata.create_all(dst_engine)

    src_inspector = inspect(src_engine)
    src_tables = set(src_inspector.get_table_names())
    Session = sessionmaker(bind=dst_engine)

    for table in TABLES:
        if table not in src_tables:
            logger.info("源库无表 %s，跳过", table)
            continue

        with src_engine.connect() as src_conn:
            rows = src_conn.execute(text(f"SELECT * FROM {table}")).mappings().all()

        if not rows:
            logger.info("表 %s 无数据，跳过", table)
            continue

        logger.info("迁移 %s: %d 行", table, len(rows))

        if dry_run:
            continue

        with Session() as session:
            for row in rows:
                payload = dict(row)
                if table == "news_intel" and payload.get("url"):
                    payload["url"] = str(payload["url"])[:512]
                session.execute(
                    text(
                        f"INSERT IGNORE INTO {table} ({', '.join(payload.keys())}) "
                        f"VALUES ({', '.join(':' + k for k in payload.keys())})"
                    ),
                    payload,
                )
            session.commit()

    logger.info("迁移完成%s", "（dry-run，未写入）" if dry_run else "")


def main() -> None:
    parser = argparse.ArgumentParser(description="问股 Agent SQLite → MySQL 迁移")
    parser.add_argument(
        "--sqlite-path",
        default="./data/stock_analysis.db",
        help="旧 SQLite 文件路径",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅统计，不写入 MySQL")
    args = parser.parse_args()
    migrate(Path(args.sqlite_path), args.dry_run)


if __name__ == "__main__":
    main()
