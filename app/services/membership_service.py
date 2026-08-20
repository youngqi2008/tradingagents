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

# 来源：data/会员等级与费用明细.xlsx
DEFAULT_LEVELS = [
    {
        "name": "体验会员",
        "code": "trial",
        "sort_order": 0,
        "monthly_free_generations": 0,
        "per_generation_price": Decimal("100.00"),
        "monthly_free_asks": 0,
        "per_ask_price": Decimal("20.00"),
        "monthly_price": Decimal("199.00"),
        "description": "了解基础功能；基础问股，含每月免费额度",
        "is_default": False,
    },
    {
        "name": "普通会员",
        "code": "normal",
        "sort_order": 1,
        "monthly_free_generations": 0,
        "per_generation_price": Decimal("90.00"),
        "monthly_free_asks": 0,
        "per_ask_price": Decimal("18.00"),
        "monthly_price": Decimal("888.00"),
        "description": "按次付费，无免费额度；无广告",
        "is_default": True,
    },
    {
        "name": "银卡会员",
        "code": "silver",
        "sort_order": 2,
        "monthly_free_generations": 0,
        "per_generation_price": Decimal("75.00"),
        "monthly_free_asks": 0,
        "per_ask_price": Decimal("15.00"),
        "monthly_price": Decimal("1888.00"),
        "description": "每月3次免费研报；优先客服，每月20次研报权益",
        "is_default": False,
    },
    {
        "name": "金卡会员",
        "code": "gold",
        "sort_order": 3,
        "monthly_free_generations": 0,
        "per_generation_price": Decimal("65.00"),
        "monthly_free_asks": 0,
        "per_ask_price": Decimal("13.00"),
        "monthly_price": Decimal("2888.00"),
        "description": "每月10次免费研报；专属客服，每月40次研报权益",
        "is_default": False,
    },
    {
        "name": "白金会员",
        "code": "platinum",
        "sort_order": 4,
        "monthly_free_generations": 0,
        "per_generation_price": Decimal("55.00"),
        "monthly_free_asks": 0,
        "per_ask_price": Decimal("11.00"),
        "monthly_price": Decimal("3888.00"),
        "description": "入门权益+每月研报5次/问股20次/AI深度分析8次；策略组合推荐",
        "is_default": False,
    },
    {
        "name": "钻石会员",
        "code": "diamond",
        "sort_order": 5,
        "monthly_free_generations": 0,
        "per_generation_price": Decimal("25.00"),
        "monthly_free_asks": 0,
        "per_ask_price": Decimal("8.00"),
        "monthly_price": Decimal("5888.00"),
        "description": "深度分析优先；每月50次AI深度分析；专属研究报告",
        "is_default": False,
    },
    {
        "name": "至尊会员",
        "code": "supreme",
        "sort_order": 6,
        "monthly_free_generations": 0,
        "per_generation_price": Decimal("15.00"),
        "monthly_free_asks": 0,
        "per_ask_price": Decimal("5.00"),
        "monthly_price": Decimal("38888.00"),
        "description": "最优权益；每月1000次问股/150次AI深度分析；1V1专属顾问",
        "is_default": False,
    },
]

DEFAULT_LEVEL_CODES = {lv["code"] for lv in DEFAULT_LEVELS}
DEPRECATED_LEVEL_CODES = {"vip"}


class MembershipService:
    async def init_default_levels(self) -> None:
        """初始化/同步默认会员等级（按 code 幂等写入）。"""
        async with get_mysql_session() as session:
            now = now_tz()
            for level in DEFAULT_LEVELS:
                result = await session.execute(
                    select(MembershipLevelORM).where(MembershipLevelORM.code == level["code"])
                )
                row = result.scalar_one_or_none()
                if row:
                    row.name = level["name"]
                    row.sort_order = level["sort_order"]
                    row.monthly_free_generations = 0
                    row.monthly_free_asks = 0
                    row.per_generation_price = level["per_generation_price"]
                    row.per_ask_price = level["per_ask_price"]
                    row.monthly_price = level["monthly_price"]
                    row.description = level["description"]
                    row.is_default = level["is_default"]
                    row.is_active = True
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

            # 确保仅一个默认等级
            default_codes = [lv["code"] for lv in DEFAULT_LEVELS if lv["is_default"]]
            if default_codes:
                await session.execute(
                    update(MembershipLevelORM)
                    .where(MembershipLevelORM.code.notin_(default_codes))
                    .values(is_default=False)
                )

            # 停用已废弃等级
            deprecated = (
                await session.execute(
                    select(MembershipLevelORM).where(MembershipLevelORM.code.in_(DEPRECATED_LEVEL_CODES))
                )
            ).scalars().all()
            for row in deprecated:
                row.is_active = False
                row.is_default = False
                row.updated_at = now

            logger.info("✅ 已同步默认会员等级（7档，免费次数归权益活动）")

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
