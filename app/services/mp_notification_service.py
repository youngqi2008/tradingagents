"""小程序站内通知服务"""

from datetime import timedelta
from typing import List, Optional, Tuple

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.mysql_db import get_mysql_session, parse_int_id
from app.models.mp_notification import MpNotificationCreate, MpNotificationResponse
from app.models.sql.models import MpNotificationORM, MpNotificationReadORM, UserORM
from app.utils.timezone import now_tz
from app.services.wechat_service import wechat_service

try:
    from tradingagents.utils.logging_manager import get_logger
except ImportError:
    import logging

    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)

logger = get_logger("mp_notification_service")

SIGNAL_NOTICE_TYPES = ("buy_signal", "sell_signal")


class MpNotificationService:
    def _retention_days(self) -> int:
        try:
            days = int(getattr(settings, "MP_NOTIFICATION_RETENTION_DAYS", 7) or 7)
        except (TypeError, ValueError):
            days = 7
        return max(0, days)

    def _retention_cutoff(self):
        days = self._retention_days()
        if days <= 0:
            return None
        return now_tz() - timedelta(days=days)

    def _retention_filter(self):
        """仅保留近 N 天消息；days<=0 时返回 None 表示不加过滤。"""
        cutoff = self._retention_cutoff()
        if cutoff is None:
            return None
        return MpNotificationORM.created_at >= cutoff

    def _user_target_filter(self, user: UserORM):
        """构建：该用户可见的已发布通知条件"""
        # target_user_ids 存 int 数组；JSON_CONTAINS 候选须为 JSON 数字，不能加引号
        user_id_json = str(int(user.id))
        conditions = [
            MpNotificationORM.status == "published",
            or_(
                MpNotificationORM.target_type == "all",
                and_(
                    MpNotificationORM.target_type == "membership",
                    MpNotificationORM.target_membership_level_id == user.membership_level_id,
                ),
                and_(
                    MpNotificationORM.target_type == "users",
                    func.json_contains(
                        MpNotificationORM.target_user_ids,
                        user_id_json,  # e.g. 123 → 仅匹配含该用户 id 的定向通知
                    ),
                ),
            ),
        ]
        retention = self._retention_filter()
        if retention is not None:
            conditions.append(retention)
        return and_(*conditions)

    async def _count_recipients(
        self,
        session: AsyncSession,
        *,
        target_type: str,
        target_membership_level_id: Optional[int],
        target_user_ids: Optional[list],
    ) -> int:
        stmt = select(func.count(UserORM.id)).where(
            UserORM.user_type == "mp_user",
            UserORM.is_active.is_(True),
        )
        if target_type == "membership" and target_membership_level_id:
            stmt = stmt.where(UserORM.membership_level_id == target_membership_level_id)
        elif target_type == "users" and target_user_ids:
            stmt = stmt.where(UserORM.id.in_(target_user_ids))
        return (await session.execute(stmt)).scalar() or 0

    async def _list_recipient_openids(
        self,
        session: AsyncSession,
        *,
        target_type: str,
        target_membership_level_id: Optional[int],
        target_user_ids: Optional[list],
    ) -> List[str]:
        stmt = select(UserORM.openid).where(
            UserORM.user_type == "mp_user",
            UserORM.is_active.is_(True),
            UserORM.openid.isnot(None),
            UserORM.openid != "",
        )
        if target_type == "membership" and target_membership_level_id:
            stmt = stmt.where(UserORM.membership_level_id == target_membership_level_id)
        elif target_type == "users" and target_user_ids:
            stmt = stmt.where(UserORM.id.in_(target_user_ids))
        rows = (await session.execute(stmt)).scalars().all()
        return [oid for oid in rows if oid and not str(oid).startswith("dev_")]

    async def _read_count(self, session: AsyncSession, notification_id: int) -> int:
        stmt = select(func.count(MpNotificationReadORM.id)).where(
            MpNotificationReadORM.notification_id == notification_id
        )
        return (await session.execute(stmt)).scalar() or 0

    def _to_response(
        self,
        row: MpNotificationORM,
        *,
        read_count: int = 0,
        is_read: Optional[bool] = None,
        read_at=None,
    ) -> MpNotificationResponse:
        user_ids = None
        if row.target_user_ids:
            user_ids = [str(x) for x in row.target_user_ids]
        return MpNotificationResponse(
            id=str(row.id),
            title=row.title,
            content=row.content,
            notice_type=row.notice_type,
            target_type=row.target_type,
            target_membership_level_id=(
                str(row.target_membership_level_id) if row.target_membership_level_id else None
            ),
            target_user_ids=user_ids,
            status=row.status,
            recipient_count=row.recipient_count,
            read_count=read_count,
            created_by=row.created_by,
            created_at=row.created_at or now_tz(),
            is_read=is_read,
            read_at=read_at,
        )

    async def create_notification(
        self, data: MpNotificationCreate, created_by: str
    ) -> MpNotificationResponse:
        target_level_id = None
        target_user_ids: Optional[list[int]] = None

        if data.target_type == "membership":
            target_level_id = parse_int_id(data.target_membership_level_id)
            if not target_level_id:
                raise ValueError("请选择目标会员等级")
        elif data.target_type == "users":
            if not data.target_user_ids:
                raise ValueError("请指定目标用户")
            target_user_ids = []
            for uid in data.target_user_ids:
                parsed = parse_int_id(uid)
                if parsed:
                    target_user_ids.append(parsed)
            if not target_user_ids:
                raise ValueError("目标用户 ID 无效")

        async with get_mysql_session() as session:
            recipient_count = await self._count_recipients(
                session,
                target_type=data.target_type,
                target_membership_level_id=target_level_id,
                target_user_ids=target_user_ids,
            )
            now = now_tz()
            row = MpNotificationORM(
                title=data.title.strip(),
                content=data.content.strip(),
                notice_type=data.notice_type or "announcement",
                target_type=data.target_type,
                target_membership_level_id=target_level_id,
                target_user_ids=target_user_ids,
                status="published",
                recipient_count=recipient_count,
                created_by=created_by,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.flush()
            await session.refresh(row)
            openids: List[str] = []
            notice_type = data.notice_type or "announcement"
            if notice_type in SIGNAL_NOTICE_TYPES:
                openids = await self._list_recipient_openids(
                    session,
                    target_type=data.target_type,
                    target_membership_level_id=target_level_id,
                    target_user_ids=target_user_ids,
                )
            logger.info(
                "站内通知已发布 id=%s target=%s recipients=%s",
                row.id,
                data.target_type,
                recipient_count,
            )
            resp = self._to_response(row, read_count=0, is_read=False)

        if notice_type in SIGNAL_NOTICE_TYPES and openids:
            title = data.title.strip()
            content = data.content.strip()
            try:
                await wechat_service.notify_signal_subscribers(
                    openids,
                    title,
                    content,
                    notice_type,
                    notice_id=str(resp.id),
                )
            except Exception:
                logger.exception("发送微信信号提醒失败 notice=%s", resp.id)
        return resp

    async def list_admin(
        self,
        skip: int = 0,
        limit: int = 50,
        *,
        notice_type: Optional[str] = None,
        created_by: Optional[str] = None,
        created_by_prefix: Optional[str] = None,
    ) -> Tuple[List[MpNotificationResponse], int]:
        async with get_mysql_session() as session:
            filters = []
            if notice_type:
                filters.append(MpNotificationORM.notice_type == notice_type)
            if created_by:
                filters.append(MpNotificationORM.created_by == created_by)
            if created_by_prefix:
                filters.append(MpNotificationORM.created_by.like(f"{created_by_prefix}%"))

            count_stmt = select(func.count(MpNotificationORM.id))
            if filters:
                count_stmt = count_stmt.where(*filters)
            total = (await session.execute(count_stmt)).scalar() or 0

            stmt = select(MpNotificationORM).order_by(MpNotificationORM.created_at.desc())
            if filters:
                stmt = stmt.where(*filters)
            stmt = stmt.offset(skip).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            items = []
            for row in rows:
                rc = await self._read_count(session, row.id)
                items.append(self._to_response(row, read_count=rc))
            return items, total

    async def revoke(self, notification_id: str) -> bool:
        nid = parse_int_id(notification_id)
        if not nid:
            return False
        async with get_mysql_session() as session:
            row = await session.get(MpNotificationORM, nid)
            if not row:
                return False
            row.status = "revoked"
            row.updated_at = now_tz()
            return True

    async def get_unread_count(
        self, user_id: str, notice_types: Optional[List[str]] = None
    ) -> int:
        uid = parse_int_id(user_id)
        if not uid:
            return 0
        async with get_mysql_session() as session:
            user = await session.get(UserORM, uid)
            if not user or user.user_type != "mp_user":
                return 0
            read_subq = (
                select(MpNotificationReadORM.notification_id)
                .where(MpNotificationReadORM.user_id == uid)
                .scalar_subquery()
            )
            filters = [
                self._user_target_filter(user),
                MpNotificationORM.id.not_in(read_subq),
            ]
            cleaned_types = [t.strip() for t in (notice_types or []) if t and t.strip()]
            if cleaned_types:
                filters.append(MpNotificationORM.notice_type.in_(cleaned_types))
            stmt = select(func.count(MpNotificationORM.id)).where(*filters)
            return (await session.execute(stmt)).scalar() or 0

    async def list_for_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
        *,
        notice_types: Optional[List[str]] = None,
    ) -> Tuple[List[MpNotificationResponse], int, int]:
        uid = parse_int_id(user_id)
        if not uid:
            return [], 0, 0
        async with get_mysql_session() as session:
            user = await session.get(UserORM, uid)
            if not user:
                return [], 0, 0

            filters = [self._user_target_filter(user)]
            cleaned_types = [t.strip() for t in (notice_types or []) if t and t.strip()]
            if cleaned_types:
                filters.append(MpNotificationORM.notice_type.in_(cleaned_types))
            base_filter = and_(*filters)

            total = (await session.execute(
                select(func.count(MpNotificationORM.id)).where(base_filter)
            )).scalar() or 0
            unread = await self.get_unread_count(user_id)

            stmt = (
                select(MpNotificationORM)
                .where(base_filter)
                .order_by(MpNotificationORM.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()

            read_map = {}
            if rows:
                ids = [r.id for r in rows]
                read_rows = (
                    await session.execute(
                        select(MpNotificationReadORM).where(
                            MpNotificationReadORM.user_id == uid,
                            MpNotificationReadORM.notification_id.in_(ids),
                        )
                    )
                ).scalars().all()
                read_map = {r.notification_id: r for r in read_rows}

            items = []
            for row in rows:
                read_row = read_map.get(row.id)
                items.append(
                    self._to_response(
                        row,
                        is_read=read_row is not None,
                        read_at=read_row.read_at if read_row else None,
                    )
                )
            return items, total, unread

    async def get_for_user(self, user_id: str, notification_id: str) -> Optional[MpNotificationResponse]:
        uid = parse_int_id(user_id)
        nid = parse_int_id(notification_id)
        if not uid or not nid:
            return None
        async with get_mysql_session() as session:
            user = await session.get(UserORM, uid)
            row = await session.get(MpNotificationORM, nid)
            if not user or not row or row.status != "published":
                return None
            if not await self._user_can_see(session, user, row):
                return None
            read_row = (
                await session.execute(
                    select(MpNotificationReadORM).where(
                        MpNotificationReadORM.user_id == uid,
                        MpNotificationReadORM.notification_id == nid,
                    )
                )
            ).scalar_one_or_none()
            return self._to_response(
                row,
                is_read=read_row is not None,
                read_at=read_row.read_at if read_row else None,
            )

    async def _user_can_see(
        self, session: AsyncSession, user: UserORM, row: MpNotificationORM
    ) -> bool:
        if row.status != "published":
            return False
        cutoff = self._retention_cutoff()
        if cutoff is not None and row.created_at and row.created_at < cutoff:
            return False
        if row.target_type == "all":
            return True
        if row.target_type == "membership":
            return user.membership_level_id == row.target_membership_level_id
        if row.target_type == "users" and row.target_user_ids:
            return user.id in row.target_user_ids
        return False

    async def cleanup_expired(self, days: Optional[int] = None) -> dict:
        """删除超过保留天数的站内消息及已读记录。"""
        retain_days = self._retention_days() if days is None else max(0, int(days))
        if retain_days <= 0:
            return {"deleted": 0, "reads_deleted": 0, "skipped": True, "reason": "retention disabled"}
        cutoff = now_tz() - timedelta(days=retain_days)
        async with get_mysql_session() as session:
            ids = (
                await session.execute(
                    select(MpNotificationORM.id).where(MpNotificationORM.created_at < cutoff)
                )
            ).scalars().all()
            if not ids:
                logger.info("🧹 小程序消息清理：无过期消息 cutoff=%s days=%s", cutoff, retain_days)
                return {
                    "deleted": 0,
                    "reads_deleted": 0,
                    "cutoff": cutoff.isoformat(),
                    "days": retain_days,
                }

            reads_result = await session.execute(
                delete(MpNotificationReadORM).where(
                    MpNotificationReadORM.notification_id.in_(ids)
                )
            )
            notif_result = await session.execute(
                delete(MpNotificationORM).where(MpNotificationORM.id.in_(ids))
            )
            deleted = notif_result.rowcount or 0
            reads_deleted = reads_result.rowcount or 0
            logger.info(
                "🧹 小程序消息清理完成: deleted=%s reads=%s cutoff=%s days=%s",
                deleted,
                reads_deleted,
                cutoff,
                retain_days,
            )
            return {
                "deleted": deleted,
                "reads_deleted": reads_deleted,
                "cutoff": cutoff.isoformat(),
                "days": retain_days,
            }

    async def mark_read(self, user_id: str, notification_id: str) -> bool:
        uid = parse_int_id(user_id)
        nid = parse_int_id(notification_id)
        if not uid or not nid:
            return False
        async with get_mysql_session() as session:
            user = await session.get(UserORM, uid)
            row = await session.get(MpNotificationORM, nid)
            if not user or not row:
                return False
            if not await self._user_can_see(session, user, row):
                return False
            exists = (
                await session.execute(
                    select(MpNotificationReadORM.id).where(
                        MpNotificationReadORM.user_id == uid,
                        MpNotificationReadORM.notification_id == nid,
                    )
                )
            ).scalar_one_or_none()
            if exists:
                return True
            session.add(
                MpNotificationReadORM(
                    notification_id=nid,
                    user_id=uid,
                    read_at=now_tz(),
                )
            )
            return True

    async def mark_all_read(self, user_id: str) -> int:
        uid = parse_int_id(user_id)
        if not uid:
            return 0
        async with get_mysql_session() as session:
            user = await session.get(UserORM, uid)
            if not user:
                return 0
            stmt = select(MpNotificationORM.id).where(self._user_target_filter(user))
            notif_ids = (await session.execute(stmt)).scalars().all()
            if not notif_ids:
                return 0
            read_ids = (
                await session.execute(
                    select(MpNotificationReadORM.notification_id).where(
                        MpNotificationReadORM.user_id == uid,
                        MpNotificationReadORM.notification_id.in_(notif_ids),
                    )
                )
            ).scalars().all()
            read_set = set(read_ids)
            count = 0
            now = now_tz()
            for nid in notif_ids:
                if nid in read_set:
                    continue
                session.add(
                    MpNotificationReadORM(
                        notification_id=nid,
                        user_id=uid,
                        read_at=now,
                    )
                )
                count += 1
            return count


mp_notification_service = MpNotificationService()
