"""
用户服务 - MySQL
"""

import hashlib
import secrets
from decimal import Decimal
from typing import Any, Dict, List, Optional

import bcrypt
from sqlalchemy import or_, select

from app.core.mysql_db import get_mysql_session, parse_int_id, reset_mysql_pool, is_stale_mysql_error
from app.models.role import DEFAULT_MP_ROLE
from app.models.sql.converters import DEFAULT_PREFERENCES, user_orm_to_pydantic, user_to_response
from app.models.sql.models import UserORM
from app.models.user import User, UserCreate, UserUpdate, UserResponse
from app.utils.timezone import now_tz

try:
    from tradingagents.utils.logging_manager import get_logger
except ImportError:
    import logging

    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)

logger = get_logger("user_service")


class UserService:
    @staticmethod
    def hash_password(password: str) -> str:
        """bcrypt 哈希（含盐）"""
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """校验密码；兼容历史 SHA256（无盐）哈希。"""
        if not hashed_password:
            return False
        # bcrypt
        if hashed_password.startswith("$2a$") or hashed_password.startswith("$2b$") or hashed_password.startswith("$2y$"):
            try:
                return bcrypt.checkpw(
                    plain_password.encode("utf-8"),
                    hashed_password.encode("utf-8"),
                )
            except (ValueError, TypeError):
                return False
        # legacy sha256
        return hashlib.sha256(plain_password.encode("utf-8")).hexdigest() == hashed_password

    @staticmethod
    def needs_rehash(hashed_password: str) -> bool:
        """历史 SHA256 哈希需在登录成功后升级为 bcrypt。"""
        if not hashed_password:
            return True
        return not (
            hashed_password.startswith("$2a$")
            or hashed_password.startswith("$2b$")
            or hashed_password.startswith("$2y$")
        )

    async def create_user(self, user_data: UserCreate) -> Optional[User]:
        try:
            async with get_mysql_session() as session:
                existing = await session.execute(
                    select(UserORM).where(UserORM.username == user_data.username)
                )
                if existing.scalar_one_or_none():
                    logger.warning(f"用户名已存在: {user_data.username}")
                    return None

                existing_email = await session.execute(
                    select(UserORM).where(UserORM.email == user_data.email)
                )
                if existing_email.scalar_one_or_none():
                    logger.warning(f"邮箱已存在: {user_data.email}")
                    return None

                now = now_tz()
                row = UserORM(
                    username=user_data.username,
                    email=user_data.email,
                    hashed_password=self.hash_password(user_data.password),
                    is_active=True,
                    is_verified=False,
                    is_admin=False,
                    user_type="admin",
                    balance=Decimal("0"),
                    preferences=DEFAULT_PREFERENCES.copy(),
                    favorite_stocks=[],
                    daily_quota=1000,
                    concurrent_limit=3,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                await session.flush()
                await session.refresh(row)
                logger.info(f"✅ 用户创建成功: {user_data.username}")
                return user_orm_to_pydantic(row)
        except Exception as e:
            logger.error(f"❌ 创建用户失败: {e}")
            return None

    async def authenticate_user(self, username: str, password: str) -> Optional[User]:
        try:
            async with get_mysql_session() as session:
                result = await session.execute(
                    select(UserORM).where(UserORM.username == username)
                )
                row = result.scalar_one_or_none()
                if not row:
                    return None
                if not self.verify_password(password, row.hashed_password):
                    return None
                if not row.is_active:
                    return None
                # 登录成功后将旧 SHA256 哈希升级为 bcrypt
                if self.needs_rehash(row.hashed_password):
                    row.hashed_password = self.hash_password(password)
                row.last_login = now_tz()
                await session.flush()
                await session.refresh(row)
                return user_orm_to_pydantic(row)
        except Exception as e:
            logger.error(f"❌ 用户认证失败: {e}")
            return None

    async def get_user_by_username(self, username: str) -> Optional[User]:
        try:
            async with get_mysql_session() as session:
                result = await session.execute(
                    select(UserORM).where(UserORM.username == username)
                )
                row = result.scalar_one_or_none()
                return user_orm_to_pydantic(row) if row else None
        except Exception as e:
            logger.error(f"❌ 获取用户失败: {e}")
            return None

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        try:
            uid = parse_int_id(user_id)
            if not uid:
                return None
            async with get_mysql_session() as session:
                row = await session.get(UserORM, uid)
                return user_orm_to_pydantic(row) if row else None
        except Exception as e:
            logger.error(f"❌ 获取用户失败: {e}")
            return None

    async def update_user(self, username: str, user_data: UserUpdate) -> Optional[User]:
        try:
            async with get_mysql_session() as session:
                result = await session.execute(
                    select(UserORM).where(UserORM.username == username)
                )
                row = result.scalar_one_or_none()
                if not row:
                    return None

                if user_data.email:
                    email_check = await session.execute(
                        select(UserORM).where(
                            UserORM.email == user_data.email,
                            UserORM.username != username,
                        )
                    )
                    if email_check.scalar_one_or_none():
                        logger.warning(f"邮箱已被使用: {user_data.email}")
                        return None
                    row.email = user_data.email

                if user_data.preferences:
                    row.preferences = user_data.preferences.model_dump()
                if user_data.daily_quota is not None:
                    row.daily_quota = user_data.daily_quota
                if user_data.concurrent_limit is not None:
                    row.concurrent_limit = user_data.concurrent_limit
                row.updated_at = now_tz()
                await session.flush()
                await session.refresh(row)
                return user_orm_to_pydantic(row)
        except Exception as e:
            logger.error(f"❌ 更新用户信息失败: {e}")
            return None

    async def change_password(self, username: str, old_password: str, new_password: str) -> bool:
        user = await self.authenticate_user(username, old_password)
        if not user:
            return False
        try:
            async with get_mysql_session() as session:
                result = await session.execute(
                    select(UserORM).where(UserORM.username == username)
                )
                row = result.scalar_one_or_none()
                if not row:
                    return False
                row.hashed_password = self.hash_password(new_password)
                row.updated_at = now_tz()
                return True
        except Exception as e:
            logger.error(f"❌ 修改密码失败: {e}")
            return False

    async def reset_password(self, username: str, new_password: str) -> bool:
        try:
            async with get_mysql_session() as session:
                result = await session.execute(
                    select(UserORM).where(UserORM.username == username)
                )
                row = result.scalar_one_or_none()
                if not row:
                    return False
                row.hashed_password = self.hash_password(new_password)
                row.updated_at = now_tz()
                return True
        except Exception as e:
            logger.error(f"❌ 重置密码失败: {e}")
            return False

    async def create_admin_user(
        self,
        username: str = "admin",
        password: str = "admin123",
        email: str = "admin@tradingagents.cn",
    ) -> Optional[User]:
        try:
            async with get_mysql_session() as session:
                result = await session.execute(
                    select(UserORM).where(UserORM.username == username)
                )
                existing = result.scalar_one_or_none()
                if existing:
                    logger.info(f"管理员用户已存在: {username}")
                    return user_orm_to_pydantic(existing)

                now = now_tz()
                row = UserORM(
                    username=username,
                    email=email,
                    hashed_password=self.hash_password(password),
                    is_active=True,
                    is_verified=True,
                    is_admin=True,
                    user_type="admin",
                    balance=Decimal("0"),
                    preferences={
                        **DEFAULT_PREFERENCES,
                        "default_depth": "深度",
                    },
                    favorite_stocks=[],
                    daily_quota=10000,
                    concurrent_limit=10,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                await session.flush()
                await session.refresh(row)
                logger.info(f"✅ 管理员用户创建成功: {username}")
                logger.info("   ⚠️  请立即修改默认密码！（密码不会写入日志）")
                return user_orm_to_pydantic(row)
        except Exception as e:
            logger.error(f"❌ 创建管理员用户失败: {e}")
            return None

    def _to_user_response(self, user: User) -> UserResponse:
        return user_to_response(user)

    async def get_user_by_openid(self, openid: str) -> Optional[User]:
        async with get_mysql_session() as session:
            result = await session.execute(
                select(UserORM).where(UserORM.openid == openid)
            )
            row = result.scalar_one_or_none()
            return user_orm_to_pydantic(row) if row else None

    async def get_or_create_mp_user(
        self,
        openid: str,
        unionid: Optional[str] = None,
        nickname: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> User:
        last_err: Optional[Exception] = None
        for attempt in range(2):
            try:
                return await self._get_or_create_mp_user_once(
                    openid=openid,
                    unionid=unionid,
                    nickname=nickname,
                    avatar_url=avatar_url,
                )
            except Exception as e:
                last_err = e
                if attempt == 0 and is_stale_mysql_error(e):
                    logger.warning(f"MySQL 死连接，重试创建/登录用户: {e}")
                    try:
                        await reset_mysql_pool()
                    except Exception as reset_err:
                        logger.error(f"重置 MySQL 连接池失败: {reset_err}")
                    continue
                logger.error(f"❌ 小程序用户登录/注册失败: {e}")
                raise
        assert last_err is not None
        raise last_err

    async def _get_or_create_mp_user_once(
        self,
        openid: str,
        unionid: Optional[str] = None,
        nickname: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> User:
        existing = await self.get_user_by_openid(openid)
        if existing:
            async with get_mysql_session() as session:
                result = await session.execute(
                    select(UserORM).where(UserORM.openid == openid)
                )
                row = result.scalar_one_or_none()
                if row:
                    row.last_login = now_tz()
                    row.updated_at = now_tz()
                    if nickname:
                        row.nickname = nickname
                    if avatar_url:
                        row.avatar_url = avatar_url
                    if unionid:
                        row.unionid = unionid
                    await session.flush()
                    await session.refresh(row)
                    return user_orm_to_pydantic(row)
            return existing

        from app.services.membership_service import membership_service

        default_level = await membership_service.get_default_level()
        level_id = default_level.id if default_level else None
        username = f"wx_{openid[-12:]}"
        suffix = 0

        async with get_mysql_session() as session:
            while True:
                result = await session.execute(
                    select(UserORM).where(UserORM.username == username)
                )
                if not result.scalar_one_or_none():
                    break
                suffix += 1
                username = f"wx_{openid[-8:]}_{suffix}"

            now = now_tz()
            row = UserORM(
                username=username,
                email=f"{openid}@mp.wechat.local",
                hashed_password=self.hash_password(secrets.token_hex(32)),
                is_active=True,
                is_verified=True,
                is_admin=False,
                user_type="mp_user",
                role=DEFAULT_MP_ROLE,
                openid=openid,
                unionid=unionid,
                nickname=nickname or f"微信用户{openid[-4:]}",
                avatar_url=avatar_url,
                membership_level_id=level_id,
                balance=Decimal("0"),
                preferences=DEFAULT_PREFERENCES.copy(),
                favorite_stocks=[],
                daily_quota=100,
                concurrent_limit=1,
                created_at=now,
                updated_at=now,
                last_login=now,
            )
            session.add(row)
            await session.flush()
            await session.refresh(row)
            logger.info(f"✅ 小程序用户创建成功: {username}")
            return user_orm_to_pydantic(row)

    async def update_mp_profile(
        self,
        user_id: str,
        *,
        nickname: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> Optional[User]:
        """更新小程序用户昵称/头像"""
        try:
            async with get_mysql_session() as session:
                result = await session.execute(
                    select(UserORM).where(
                        UserORM.id == user_id,
                        UserORM.user_type == "mp_user",
                    )
                )
                row = result.scalar_one_or_none()
                if not row:
                    return None
                if nickname is not None:
                    row.nickname = nickname.strip() or row.nickname
                if avatar_url is not None:
                    row.avatar_url = avatar_url
                row.updated_at = now_tz()
                await session.flush()
                await session.refresh(row)
                return user_orm_to_pydantic(row)
        except Exception as e:
            logger.error(f"❌ 更新小程序用户资料失败: {e}")
            return None

    async def get_mp_user_id_map(self) -> Dict[str, Dict[str, str]]:
        """返回小程序用户 id -> {nickname, openid} 映射，供运营任务列表关联展示"""
        try:
            async with get_mysql_session() as session:
                stmt = select(
                    UserORM.id,
                    UserORM.nickname,
                    UserORM.openid,
                    UserORM.username,
                ).where(UserORM.user_type == "mp_user")
                rows = (await session.execute(stmt)).all()
                return {
                    str(r.id): {
                        "nickname": r.nickname or r.username or "",
                        "openid": r.openid or "",
                    }
                    for r in rows
                }
        except Exception as e:
            logger.error(f"❌ 获取小程序用户映射失败: {e}")
            return {}

    async def get_mp_user(self, user_id: str) -> Optional[UserResponse]:
        user = await self.get_user_by_id(user_id)
        if not user or user.user_type != "mp_user":
            return None
        return self._to_user_response(user)

    async def count_mp_users(
        self,
        keyword: Optional[str] = None,
        role: Optional[str] = None,
    ) -> int:
        try:
            from sqlalchemy import func

            async with get_mysql_session() as session:
                stmt = select(func.count(UserORM.id)).where(UserORM.user_type == "mp_user")
                if role:
                    stmt = stmt.where(UserORM.role == role)
                if keyword:
                    pattern = f"%{keyword}%"
                    stmt = stmt.where(
                        or_(
                            UserORM.nickname.like(pattern),
                            UserORM.openid.like(pattern),
                            UserORM.phone.like(pattern),
                        )
                    )
                return (await session.execute(stmt)).scalar() or 0
        except Exception as e:
            logger.error(f"❌ 统计小程序用户失败: {e}")
            return 0

    async def list_mp_users(
        self,
        skip: int = 0,
        limit: int = 50,
        keyword: Optional[str] = None,
        role: Optional[str] = None,
    ) -> List[UserResponse]:
        try:
            async with get_mysql_session() as session:
                stmt = (
                    select(UserORM)
                    .where(UserORM.user_type == "mp_user")
                    .order_by(UserORM.created_at.desc())
                    .offset(skip)
                    .limit(limit)
                )
                if role:
                    stmt = stmt.where(UserORM.role == role)
                if keyword:
                    pattern = f"%{keyword}%"
                    stmt = stmt.where(
                        or_(
                            UserORM.nickname.like(pattern),
                            UserORM.openid.like(pattern),
                            UserORM.phone.like(pattern),
                        )
                    )
                rows = (await session.execute(stmt)).scalars().all()
                return [self._to_user_response(user_orm_to_pydantic(r)) for r in rows]
        except Exception as e:
            logger.error(f"❌ 获取小程序用户列表失败: {e}")
            return []

    async def update_mp_user_membership(self, user_id: str, membership_level_id: str) -> bool:
        uid = parse_int_id(user_id)
        lid = parse_int_id(membership_level_id)
        if not uid or not lid:
            return False
        try:
            async with get_mysql_session() as session:
                row = await session.get(UserORM, uid)
                if not row or row.user_type != "mp_user":
                    return False
                row.membership_level_id = lid
                row.updated_at = now_tz()
                return True
        except Exception as e:
            logger.error(f"❌ 更新会员等级失败: {e}")
            return False

    async def update_mp_user_role(self, user_id: str, role: str) -> bool:
        """授予/变更小程序用户角色"""
        from app.services.role_service import role_service

        uid = parse_int_id(user_id)
        if not uid:
            return False
        if not await role_service.is_valid_role(role):
            return False
        try:
            async with get_mysql_session() as session:
                row = await session.get(UserORM, uid)
                if not row or row.user_type != "mp_user":
                    return False
                row.role = role
                row.updated_at = now_tz()
                return True
        except Exception as e:
            logger.error(f"❌ 更新用户角色失败: {e}")
            return False

    async def grant_mp_user_roles(self, user_ids: List[str], role: str) -> Dict[str, int]:
        """批量授予角色，返回 success/failed/skipped 计数"""
        from app.services.role_service import role_service

        result = {"success": 0, "failed": 0, "skipped": 0}
        if not await role_service.is_valid_role(role):
            result["failed"] = len(user_ids)
            return result

        uids = [uid for uid in (parse_int_id(x) for x in user_ids) if uid]
        if not uids:
            result["failed"] = len(user_ids)
            return result

        try:
            async with get_mysql_session() as session:
                rows = (
                    await session.execute(
                        select(UserORM).where(
                            UserORM.id.in_(uids),
                            UserORM.user_type == "mp_user",
                        )
                    )
                ).scalars().all()
                found_ids = {r.id for r in rows}
                now = now_tz()
                for row in rows:
                    if row.role == role:
                        result["skipped"] += 1
                        continue
                    row.role = role
                    row.updated_at = now
                    result["success"] += 1
                result["failed"] += len(uids) - len(found_ids)
                # 请求里无法解析的 id
                result["failed"] += max(0, len(user_ids) - len(uids))
            return result
        except Exception as e:
            logger.error(f"❌ 批量授予角色失败: {e}")
            result["failed"] = len(user_ids)
            result["success"] = 0
            result["skipped"] = 0
            return result

    async def set_mp_user_active(self, user_id: str, is_active: bool) -> bool:
        uid = parse_int_id(user_id)
        if not uid:
            return False
        try:
            async with get_mysql_session() as session:
                row = await session.get(UserORM, uid)
                if not row or row.user_type != "mp_user":
                    return False
                row.is_active = is_active
                row.updated_at = now_tz()
                return True
        except Exception as e:
            logger.error(f"❌ 更新用户状态失败: {e}")
            return False

    async def list_users(self, skip: int = 0, limit: int = 100) -> List[UserResponse]:
        try:
            async with get_mysql_session() as session:
                stmt = select(UserORM).offset(skip).limit(limit)
                rows = (await session.execute(stmt)).scalars().all()
                return [self._to_user_response(user_orm_to_pydantic(r)) for r in rows]
        except Exception as e:
            logger.error(f"❌ 获取用户列表失败: {e}")
            return []

    async def deactivate_user(self, username: str) -> bool:
        return await self._set_user_active(username, False)

    async def activate_user(self, username: str) -> bool:
        return await self._set_user_active(username, True)

    async def _set_user_active(self, username: str, is_active: bool) -> bool:
        try:
            async with get_mysql_session() as session:
                result = await session.execute(
                    select(UserORM).where(UserORM.username == username)
                )
                row = result.scalar_one_or_none()
                if not row:
                    return False
                row.is_active = is_active
                row.updated_at = now_tz()
                return True
        except Exception as e:
            logger.error(f"❌ 更新用户状态失败: {e}")
            return False


user_service = UserService()
