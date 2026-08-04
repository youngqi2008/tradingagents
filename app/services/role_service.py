"""小程序角色服务 - MySQL"""

from typing import Dict, List, Optional

from sqlalchemy import func, select, update

from app.core.mysql_db import get_mysql_session, parse_int_id
from app.models.role import (
    DEFAULT_MP_ROLE,
    DEFAULT_MP_ROLES,
    RoleCreate,
    RoleInfo,
    RoleUpdate,
    role_display_name,
)
from app.models.sql.models import RoleORM, UserORM
from app.utils.timezone import now_tz

try:
    from tradingagents.utils.logging_manager import get_logger
except ImportError:
    import logging

    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)

logger = get_logger("role_service")

# 名称缓存，供同步转换使用
_role_name_cache: Dict[str, str] = {r["code"]: r["name"] for r in DEFAULT_MP_ROLES}
_active_role_codes: set[str] = {r["code"] for r in DEFAULT_MP_ROLES}


class RoleService:
    async def init_default_roles(self) -> None:
        """幂等写入内置角色：普通 / 风控专员"""
        async with get_mysql_session() as session:
            now = now_tz()
            for item in DEFAULT_MP_ROLES:
                result = await session.execute(
                    select(RoleORM).where(RoleORM.code == item["code"])
                )
                row = result.scalar_one_or_none()
                if row:
                    if not row.description:
                        row.description = item["description"]
                    row.updated_at = now
                    continue
                session.add(
                    RoleORM(
                        name=item["name"],
                        code=item["code"],
                        description=item["description"],
                        sort_order=item["sort_order"],
                        is_default=item["is_default"],
                        is_active=True,
                        created_at=now,
                        updated_at=now,
                    )
                )
            logger.info("✅ 已同步默认小程序角色")
        await self.refresh_cache()

    async def refresh_cache(self) -> None:
        global _role_name_cache, _active_role_codes
        async with get_mysql_session() as session:
            rows = (await session.execute(select(RoleORM))).scalars().all()
            _role_name_cache = {r.code: r.name for r in rows}
            _active_role_codes = {r.code for r in rows if r.is_active}

    def get_name_map(self) -> Dict[str, str]:
        return dict(_role_name_cache)

    def display_name(self, role: Optional[str]) -> str:
        return role_display_name(role, _role_name_cache)

    async def is_valid_role(self, role: Optional[str], *, active_only: bool = True) -> bool:
        if not role:
            return False
        if role in _active_role_codes:
            return True
        # 缓存可能过期，查库
        async with get_mysql_session() as session:
            stmt = select(RoleORM).where(RoleORM.code == role)
            if active_only:
                stmt = stmt.where(RoleORM.is_active.is_(True))
            row = (await session.execute(stmt)).scalar_one_or_none()
            return row is not None

    async def list_roles(self, active_only: bool = False) -> List[RoleInfo]:
        async with get_mysql_session() as session:
            stmt = select(RoleORM).order_by(RoleORM.sort_order, RoleORM.id)
            if active_only:
                stmt = stmt.where(RoleORM.is_active.is_(True))
            rows = (await session.execute(stmt)).scalars().all()

            counts: Dict[str, int] = {}
            count_rows = (
                await session.execute(
                    select(UserORM.role, func.count(UserORM.id))
                    .where(UserORM.user_type == "mp_user")
                    .group_by(UserORM.role)
                )
            ).all()
            for code, cnt in count_rows:
                counts[code or DEFAULT_MP_ROLE] = int(cnt or 0)

            return [
                RoleInfo(
                    id=str(r.id),
                    code=r.code,
                    name=r.name,
                    description=r.description or "",
                    sort_order=r.sort_order,
                    is_default=r.is_default,
                    is_active=r.is_active,
                    user_count=counts.get(r.code, 0),
                )
                for r in rows
            ]

    async def get_by_code(self, code: str) -> Optional[RoleInfo]:
        async with get_mysql_session() as session:
            row = (
                await session.execute(select(RoleORM).where(RoleORM.code == code))
            ).scalar_one_or_none()
            if not row:
                return None
            return RoleInfo(
                id=str(row.id),
                code=row.code,
                name=row.name,
                description=row.description or "",
                sort_order=row.sort_order,
                is_default=row.is_default,
                is_active=row.is_active,
            )

    async def create_role(self, data: RoleCreate) -> RoleInfo:
        code = data.code.strip().lower()
        if not code.replace("_", "").isalnum():
            raise ValueError("角色编码仅支持字母、数字和下划线")
        async with get_mysql_session() as session:
            exists = (
                await session.execute(select(RoleORM).where(RoleORM.code == code))
            ).scalar_one_or_none()
            if exists:
                raise ValueError("角色编码已存在")

            now = now_tz()
            if data.is_default:
                await session.execute(
                    update(RoleORM).values(is_default=False, updated_at=now)
                )

            row = RoleORM(
                name=data.name.strip(),
                code=code,
                description=(data.description or "").strip(),
                sort_order=data.sort_order,
                is_default=data.is_default,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.flush()
            await session.refresh(row)
            result = RoleInfo(
                id=str(row.id),
                code=row.code,
                name=row.name,
                description=row.description or "",
                sort_order=row.sort_order,
                is_default=row.is_default,
                is_active=row.is_active,
            )
        await self.refresh_cache()
        return result

    async def update_role(self, role_id: str, data: RoleUpdate) -> Optional[RoleInfo]:
        rid = parse_int_id(role_id)
        if not rid:
            return None
        async with get_mysql_session() as session:
            row = await session.get(RoleORM, rid)
            if not row:
                return None
            now = now_tz()
            if data.name is not None:
                row.name = data.name.strip()
            if data.description is not None:
                row.description = data.description.strip()
            if data.sort_order is not None:
                row.sort_order = data.sort_order
            if data.is_active is not None:
                if row.is_default and data.is_active is False:
                    raise ValueError("默认角色不可停用")
                row.is_active = data.is_active
            if data.is_default is True:
                await session.execute(
                    update(RoleORM)
                    .where(RoleORM.id != rid)
                    .values(is_default=False, updated_at=now)
                )
                row.is_default = True
            elif data.is_default is False and row.is_default:
                raise ValueError("请先将其他角色设为默认，再取消当前默认")
            row.updated_at = now
            await session.flush()
            await session.refresh(row)
            result = RoleInfo(
                id=str(row.id),
                code=row.code,
                name=row.name,
                description=row.description or "",
                sort_order=row.sort_order,
                is_default=row.is_default,
                is_active=row.is_active,
            )
        await self.refresh_cache()
        return result

    async def deactivate_role(self, role_id: str) -> bool:
        """停用角色，并将已授予该角色的小程序用户降为默认普通角色。"""
        rid = parse_int_id(role_id)
        if not rid:
            return False
        async with get_mysql_session() as session:
            row = await session.get(RoleORM, rid)
            if not row:
                return False
            if row.is_default:
                raise ValueError("默认角色不可停用")
            code = row.code
            now = now_tz()
            row.is_active = False
            row.updated_at = now
            # 批量回收权限
            demoted = await session.execute(
                update(UserORM)
                .where(
                    UserORM.user_type == "mp_user",
                    UserORM.role == code,
                )
                .values(role=DEFAULT_MP_ROLE, updated_at=now)
            )
            logger.info(
                "角色已停用 code=%s，已降级用户数≈%s",
                code,
                demoted.rowcount if demoted.rowcount is not None else "?",
            )
        await self.refresh_cache()
        return True


role_service = RoleService()
