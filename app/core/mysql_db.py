"""MySQL 连接（用户/计费/问股 Agent 共用）"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from urllib.parse import quote_plus

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

logger = logging.getLogger(__name__)

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def build_mysql_url(driver: str) -> str:
    user = quote_plus(settings.MYSQL_USER)
    password = quote_plus(settings.MYSQL_PASSWORD)
    return (
        f"{driver}://{user}:{password}"
        f"@{settings.MYSQL_HOST}:{settings.MYSQL_PORT}/{settings.MYSQL_DATABASE}"
        f"?charset=utf8mb4"
    )


def get_mysql_url() -> str:
    return build_mysql_url("mysql+aiomysql")


def get_sync_mysql_url() -> str:
    """问股 Agent 同步 SQLAlchemy 连接（pymysql）"""
    return build_mysql_url("mysql+pymysql")


async def init_mysql() -> None:
    global _engine, _session_factory
    if _engine is not None:
        return

    logger.info("🔄 正在初始化 MySQL 连接...")
    _engine = create_async_engine(
        get_mysql_url(),
        pool_size=settings.MYSQL_POOL_SIZE,
        max_overflow=settings.MYSQL_MAX_OVERFLOW,
        pool_pre_ping=True,
        pool_recycle=1800,  # 避免远端 MySQL 空闲断开后连接池仍持有死连接
        echo=settings.DEBUG and False,
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)

    from app.models.sql.models import Base
    from app.stock_agent.dsa_storage import Base as StockAgentBase

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(StockAgentBase.metadata.create_all)
        await conn.run_sync(_migrate_membership_schema)
        await conn.run_sync(_migrate_user_role_schema)
        await conn.run_sync(_migrate_wx_session_key)
    
    logger.info(f"✅ MySQL 连接成功: {settings.MYSQL_HOST}:{settings.MYSQL_PORT}/{settings.MYSQL_DATABASE}")


def _migrate_wx_session_key(connection) -> None:
    """增量迁移：保存小程序 session_key，供虚拟支付用户态签名使用。"""
    from sqlalchemy import inspect, text

    insp = inspect(connection)
    if not insp.has_table("users"):
        return
    user_cols = {c["name"] for c in insp.get_columns("users")}
    if "wx_session_key" not in user_cols:
        connection.execute(
            text("ALTER TABLE users ADD COLUMN wx_session_key VARCHAR(256) NULL AFTER unionid")
        )


def _migrate_user_role_schema(connection) -> None:
    """增量迁移：小程序用户角色（普通 / 风控专员）"""
    from sqlalchemy import inspect, text

    insp = inspect(connection)
    if not insp.has_table("users"):
        return

    user_cols = {c["name"] for c in insp.get_columns("users")}
    if "role" not in user_cols:
        connection.execute(
            text(
                "ALTER TABLE users "
                "ADD COLUMN role VARCHAR(32) NOT NULL DEFAULT 'normal' AFTER user_type"
            )
        )
        connection.execute(
            text(
                "UPDATE users SET role = 'normal' "
                "WHERE user_type = 'mp_user' AND (role IS NULL OR role = '')"
            )
        )


def _migrate_membership_schema(connection) -> None:
    """增量迁移：会员问股/研报分开额度、月费字段"""
    from sqlalchemy import inspect, text

    insp = inspect(connection)
    if not insp.has_table("membership_levels"):
        return

    level_cols = {c["name"] for c in insp.get_columns("membership_levels")}
    if "monthly_free_asks" not in level_cols:
        connection.execute(
            text(
                "ALTER TABLE membership_levels "
                "ADD COLUMN monthly_free_asks INT NOT NULL DEFAULT 0 AFTER per_generation_price"
            )
        )
    if "per_ask_price" not in level_cols:
        connection.execute(
            text(
                "ALTER TABLE membership_levels "
                "ADD COLUMN per_ask_price DECIMAL(10, 2) NOT NULL DEFAULT 9.90 AFTER monthly_free_asks"
            )
        )
        connection.execute(
            text("UPDATE membership_levels SET per_ask_price = per_generation_price")
        )
    if "monthly_price" in level_cols:
        connection.execute(
            text("UPDATE membership_levels SET monthly_price = 0 WHERE monthly_price IS NULL")
        )

    if not insp.has_table("user_quota_usage"):
        return

    quota_cols = {c["name"] for c in insp.get_columns("user_quota_usage")}
    if "free_asks_used" not in quota_cols:
        connection.execute(
            text(
                "ALTER TABLE user_quota_usage "
                "ADD COLUMN free_asks_used INT NOT NULL DEFAULT 0 AFTER free_generations_used"
            )
        )
    if "membership_fee_charged" not in quota_cols:
        connection.execute(
            text(
                "ALTER TABLE user_quota_usage "
                "ADD COLUMN membership_fee_charged TINYINT(1) NOT NULL DEFAULT 0 AFTER free_asks_used"
            )
        )

    # 权益活动：默认授予 / 增加授予
    if insp.has_table("benefit_campaigns"):
        campaign_cols = {c["name"] for c in insp.get_columns("benefit_campaigns")}
        if "grant_mode" not in campaign_cols:
            connection.execute(
                text(
                    "ALTER TABLE benefit_campaigns "
                    "ADD COLUMN grant_mode VARCHAR(16) NOT NULL DEFAULT 'addon' AFTER grant_scope"
                )
            )
            # 系统种子活动（level_*）视为默认授予；其余保持 addon
            connection.execute(
                text(
                    "UPDATE benefit_campaigns SET grant_mode = 'default' "
                    "WHERE code LIKE 'level_%'"
                )
            )


async def close_mysql() -> None:
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("✅ MySQL 连接已关闭")


async def reset_mysql_pool() -> None:
    """丢弃连接池并重新初始化（用于死连接 / TCPTransport closed）。"""
    logger.warning("⚠️ 重置 MySQL 连接池...")
    await close_mysql()
    await init_mysql()


def is_stale_mysql_error(exc: BaseException) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    markers = (
        "tcptransport closed",
        "connection is closed",
        "connection reset",
        "lost connection",
        "server has gone away",
        "broken pipe",
        "can't connect",
        "connection refused",
        "not connected",
        "packet sequence number wrong",
    )
    return any(m in text for m in markers)


@asynccontextmanager
async def mysql_session() -> AsyncGenerator[AsyncSession, None]:
    """获取 Session（不自动 commit，由调用方控制事务）"""
    if _session_factory is None:
        raise RuntimeError("MySQL 未初始化，请先调用 init_mysql()")
    session = _session_factory()
    try:
        yield session
    finally:
        await session.close()


@asynccontextmanager
async def get_mysql_session() -> AsyncGenerator[AsyncSession, None]:
    """获取 Session 并在成功时自动 commit"""
    async with mysql_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def parse_int_id(value: str | int | None) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
