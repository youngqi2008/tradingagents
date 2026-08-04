"""会员等级服务 - MySQL"""

from decimal import Decimal
from typing import List, Optional

from sqlalchemy import select, update

from app.core.mysql_db import get_mysql_session, parse_int_id
from app.models.membership import (
    MembershipLevel,
    MembershipLevelCreate,
    MembershipLevelUpdate,
    MembershipLevelResponse,
)
from app.models.sql.converters import membership_orm_to_pydantic, membership_to_response
from app.models.sql.models import MembershipLevelORM
from app.utils.timezone import now_tz

try:
    from tradingagents.utils.logging_manager import get_logger
except ImportError:
    import logging
    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)

logger = get_logger("membership_service")

DEFAULT_LEVELS = [
    {
        "name": "普通会员",
        "code": "normal",
        "sort_order": 0,
        # 免费次数改由「客户权益」发放；等级本身只定单价与月费
        "monthly_free_generations": 0,
        "per_generation_price": Decimal("9.90"),
        "monthly_free_asks": 0,
        "per_ask_price": Decimal("1.90"),
        "monthly_price": Decimal("0"),
        "description": "入门权益：一次性研报5次、问股8次；用尽后按次付费",
        "is_default": True,
    },
    {
        "name": "银卡会员",
        "code": "silver",
        "sort_order": 1,
        "monthly_free_generations": 0,
        "per_generation_price": Decimal("7.90"),
        "monthly_free_asks": 0,
        "per_ask_price": Decimal("1.20"),
        "monthly_price": Decimal("19.90"),
        "description": "入门权益 + 每月研报3次/问股12次/推送3次；月费19.9元",
        "is_default": False,
    },
    {
        "name": "VIP会员",
        "code": "vip",
        "sort_order": 2,
        "monthly_free_generations": 0,
        "per_generation_price": Decimal("6.90"),
        "monthly_free_asks": 0,
        "per_ask_price": Decimal("0.90"),
        "monthly_price": Decimal("29.90"),
        "description": "入门权益 + 每月研报5次/问股20次/推送8次；月费29.9元",
        "is_default": False,
    },
]


class MembershipService:
    async def init_default_levels(self) -> None:
        """初始化/补齐默认会员等级（按 code 幂等写入，不覆盖运营已改单价以外的结构）。"""
        async with get_mysql_session() as session:
            now = now_tz()
            for level in DEFAULT_LEVELS:
                result = await session.execute(
                    select(MembershipLevelORM).where(MembershipLevelORM.code == level["code"])
                )
                row = result.scalar_one_or_none()
                if row:
                    # 将免费次数归零，统一走权益活动；保留运营可能改过的价格
                    row.monthly_free_generations = 0
                    row.monthly_free_asks = 0
                    if not row.description:
                        row.description = level["description"]
                    row.updated_at = now
                    continue
                session.add(
                    MembershipLevelORM(
                        name=level["name"],
                        code=level["code"],
                        sort_order=level["sort_order"],
                        monthly_free_generations=0,
                        per_generation_price=level["per_generation_price"],
                        monthly_free_asks=0,
                        per_ask_price=level["per_ask_price"],
                        monthly_price=level["monthly_price"],
                        description=level["description"],
                        is_default=level["is_default"],
                        is_active=True,
                        created_at=now,
                        updated_at=now,
                    )
                )
            logger.info("✅ 已同步默认会员等级（免费次数归权益活动）")

    async def list_levels(self, active_only: bool = False) -> List[MembershipLevelResponse]:
        async with get_mysql_session() as session:
            stmt = select(MembershipLevelORM).order_by(MembershipLevelORM.sort_order)
            if active_only:
                stmt = stmt.where(MembershipLevelORM.is_active.is_(True))
            rows = (await session.execute(stmt)).scalars().all()
            return [membership_to_response(r) for r in rows]

    async def get_level_by_id(self, level_id: str) -> Optional[MembershipLevel]:
        lid = parse_int_id(level_id)
        if not lid:
            return None
        async with get_mysql_session() as session:
            row = await session.get(MembershipLevelORM, lid)
            return membership_orm_to_pydantic(row) if row else None

    async def get_default_level(self) -> Optional[MembershipLevel]:
        async with get_mysql_session() as session:
            result = await session.execute(
                select(MembershipLevelORM)
                .where(MembershipLevelORM.is_default.is_(True), MembershipLevelORM.is_active.is_(True))
                .limit(1)
            )
            row = result.scalar_one_or_none()
            if not row:
                result = await session.execute(
                    select(MembershipLevelORM)
                    .where(MembershipLevelORM.is_active.is_(True))
                    .order_by(MembershipLevelORM.sort_order)
                    .limit(1)
                )
                row = result.scalar_one_or_none()
            return membership_orm_to_pydantic(row) if row else None

    async def create_level(self, data: MembershipLevelCreate) -> Optional[MembershipLevelResponse]:
        async with get_mysql_session() as session:
            exists = await session.execute(
                select(MembershipLevelORM).where(MembershipLevelORM.code == data.code)
            )
            if exists.scalar_one_or_none():
                return None
            if data.is_default:
                await session.execute(update(MembershipLevelORM).values(is_default=False))
            now = now_tz()
            row = MembershipLevelORM(
                name=data.name,
                code=data.code,
                sort_order=data.sort_order,
                monthly_free_generations=data.monthly_free_generations,
                per_generation_price=data.per_generation_price,
                monthly_free_asks=data.monthly_free_asks,
                per_ask_price=data.per_ask_price,
                monthly_price=data.monthly_price,
                description=data.description,
                is_default=data.is_default,
                is_active=data.is_active,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.flush()
            await session.refresh(row)
            return membership_to_response(row)

    async def update_level(self, level_id: str, data: MembershipLevelUpdate) -> Optional[MembershipLevelResponse]:
        lid = parse_int_id(level_id)
        if not lid:
            return None
        async with get_mysql_session() as session:
            row = await session.get(MembershipLevelORM, lid)
            if not row:
                return None
            update_data = data.model_dump(exclude_unset=True)
            if not update_data:
                return membership_to_response(row)
            if update_data.get("is_default"):
                await session.execute(update(MembershipLevelORM).values(is_default=False))
            for k, v in update_data.items():
                setattr(row, k, v)
            row.updated_at = now_tz()
            await session.flush()
            await session.refresh(row)
            return membership_to_response(row)

    async def delete_level(self, level_id: str) -> bool:
        lid = parse_int_id(level_id)
        if not lid:
            return False
        async with get_mysql_session() as session:
            row = await session.get(MembershipLevelORM, lid)
            if not row or row.is_default:
                return False
            row.is_active = False
            row.updated_at = now_tz()
            return True


membership_service = MembershipService()
