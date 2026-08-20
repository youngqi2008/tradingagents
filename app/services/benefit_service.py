"""客户权益 / 活动服务：定义、发放、叠加扣减"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional, Literal

from sqlalchemy import select

from app.core.mysql_db import get_mysql_session, mysql_session, parse_int_id
from app.models.benefit import (
    AssignBenefitRequest,
    BenefitCampaignCreate,
    BenefitCampaignResponse,
    BenefitCampaignUpdate,
    UserBenefitGrantResponse,
)
from app.models.sql.models import BenefitCampaignORM, UserBenefitGrantORM, UserORM
from app.utils.timezone import ensure_timezone, now_tz

try:
    from tradingagents.utils.logging_manager import get_logger
except ImportError:
    import logging

    def get_logger(name: str):
        return logging.getLogger(name)

logger = get_logger("benefit_service")

BenefitKind = Literal["report", "ask", "push"]


def _campaign_to_resp(row: BenefitCampaignORM) -> BenefitCampaignResponse:
    return BenefitCampaignResponse(
        id=str(row.id),
        name=row.name,
        code=row.code,
        description=row.description or "",
        status=row.status,
        grant_scope=row.grant_scope,
        grant_mode=getattr(row, "grant_mode", None) or "addon",
        membership_level_id=str(row.membership_level_id) if row.membership_level_id else None,
        cycle_type=row.cycle_type,
        start_at=row.start_at,
        end_at=row.end_at,
        report_quota=row.report_quota or 0,
        ask_quota=row.ask_quota or 0,
        push_quota=row.push_quota or 0,
        stackable=bool(row.stackable),
        priority=row.priority or 100,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _validate_grant_mode_scope(grant_mode: str, grant_scope: str) -> None:
    """默认授予仅允许 membership/all；增加授予可任意范围（含单用户 manual）。"""
    if grant_mode == "default" and grant_scope not in ("membership", "all"):
        raise ValueError("默认授予仅支持「会员等级」或「全体用户」范围")
    if grant_mode not in ("default", "addon"):
        raise ValueError("grant_mode 须为 default 或 addon")


def _grant_to_resp(row: UserBenefitGrantORM, campaign: Optional[BenefitCampaignORM] = None) -> UserBenefitGrantResponse:
    return UserBenefitGrantResponse(
        id=str(row.id),
        user_id=str(row.user_id),
        campaign_id=str(row.campaign_id),
        campaign_name=campaign.name if campaign else "",
        campaign_code=campaign.code if campaign else "",
        source=row.source,
        cycle_key=row.cycle_key,
        report_limit=row.report_limit,
        ask_limit=row.ask_limit,
        push_limit=row.push_limit,
        report_used=row.report_used,
        ask_used=row.ask_used,
        push_used=row.push_used,
        report_remaining=max(0, row.report_limit - row.report_used),
        ask_remaining=max(0, row.ask_limit - row.ask_used),
        push_remaining=max(0, row.push_limit - row.push_used),
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        status=row.status,
        remark=row.remark or "",
        created_at=row.created_at,
    )


class BenefitService:
    @staticmethod
    def _as_aware(dt: Optional[datetime], ref: Optional[datetime] = None) -> Optional[datetime]:
        """MySQL 常返回 naive datetime；与 now_tz() 比较前统一为 aware。"""
        if dt is None:
            return None
        if dt.tzinfo is not None:
            return dt
        # 优先跟 now 同一时区；否则走配置时区
        if ref is not None and ref.tzinfo is not None:
            return dt.replace(tzinfo=ref.tzinfo)
        return ensure_timezone(dt)

    def _cycle_key(self, cycle_type: str, now: Optional[datetime] = None) -> str:
        now = now or now_tz()
        if cycle_type == "daily":
            return now.strftime("%Y-%m-%d")
        if cycle_type == "monthly":
            return now.strftime("%Y-%m")
        return "once"

    def _campaign_window_ok(self, camp: BenefitCampaignORM, now: datetime) -> bool:
        start_at = self._as_aware(camp.start_at, now)
        end_at = self._as_aware(camp.end_at, now)
        if start_at and now < start_at:
            return False
        if end_at and now > end_at:
            return False
        return True

    def _grant_valid(self, grant: UserBenefitGrantORM, now: datetime) -> bool:
        if grant.status not in ("active",):
            return False
        valid_from = self._as_aware(grant.valid_from, now)
        valid_to = self._as_aware(grant.valid_to, now)
        if valid_from and now < valid_from:
            return False
        if valid_to and now > valid_to:
            return False
        return True

    def _kind_remaining(self, grant: UserBenefitGrantORM, kind: BenefitKind) -> int:
        if kind == "ask":
            return max(0, grant.ask_limit - grant.ask_used)
        if kind == "push":
            return max(0, grant.push_limit - grant.push_used)
        return max(0, grant.report_limit - grant.report_used)

    async def list_campaigns(
        self,
        *,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[BenefitCampaignResponse]:
        async with get_mysql_session() as session:
            q = select(BenefitCampaignORM).order_by(
                BenefitCampaignORM.priority.asc(), BenefitCampaignORM.id.desc()
            )
            if status:
                q = q.where(BenefitCampaignORM.status == status)
            q = q.offset(skip).limit(limit)
            rows = (await session.execute(q)).scalars().all()
            return [_campaign_to_resp(r) for r in rows]

    async def get_campaign(self, campaign_id: str) -> Optional[BenefitCampaignResponse]:
        cid = parse_int_id(campaign_id)
        if not cid:
            return None
        async with get_mysql_session() as session:
            row = await session.get(BenefitCampaignORM, cid)
            return _campaign_to_resp(row) if row else None

    async def create_campaign(self, payload: BenefitCampaignCreate) -> BenefitCampaignResponse:
        async with mysql_session() as session:
            async with session.begin():
                exists = await session.execute(
                    select(BenefitCampaignORM).where(BenefitCampaignORM.code == payload.code)
                )
                if exists.scalar_one_or_none():
                    raise ValueError(f"活动代码已存在: {payload.code}")
                mid = parse_int_id(payload.membership_level_id) if payload.membership_level_id else None
                if payload.grant_scope == "membership" and not mid:
                    raise ValueError("会员等级活动必须指定 membership_level_id")
                _validate_grant_mode_scope(payload.grant_mode, payload.grant_scope)
                row = BenefitCampaignORM(
                    name=payload.name,
                    code=payload.code,
                    description=payload.description or "",
                    status=payload.status,
                    grant_scope=payload.grant_scope,
                    grant_mode=payload.grant_mode,
                    membership_level_id=mid,
                    cycle_type=payload.cycle_type,
                    start_at=payload.start_at,
                    end_at=payload.end_at,
                    report_quota=payload.report_quota,
                    ask_quota=payload.ask_quota,
                    push_quota=payload.push_quota,
                    stackable=payload.stackable,
                    priority=payload.priority,
                )
                session.add(row)
                await session.flush()
                await session.refresh(row)
                logger.info(f"✅ 创建权益活动: {row.code} mode={row.grant_mode}")
                return _campaign_to_resp(row)

    async def update_campaign(
        self, campaign_id: str, payload: BenefitCampaignUpdate
    ) -> Optional[BenefitCampaignResponse]:
        cid = parse_int_id(campaign_id)
        if not cid:
            return None
        async with mysql_session() as session:
            async with session.begin():
                row = await session.get(BenefitCampaignORM, cid)
                if not row:
                    return None
                data = payload.model_dump(exclude_unset=True)
                if "membership_level_id" in data:
                    data["membership_level_id"] = (
                        parse_int_id(data["membership_level_id"]) if data["membership_level_id"] else None
                    )
                next_scope = data.get("grant_scope", row.grant_scope)
                next_mode = data.get("grant_mode", getattr(row, "grant_mode", None) or "addon")
                if "grant_scope" in data or "grant_mode" in data:
                    _validate_grant_mode_scope(next_mode, next_scope)
                if next_scope == "membership":
                    mid = data.get("membership_level_id", row.membership_level_id)
                    if not mid:
                        raise ValueError("会员等级活动必须指定 membership_level_id")
                for k, v in data.items():
                    setattr(row, k, v)
                row.updated_at = now_tz()
                await session.flush()
                await session.refresh(row)
                return _campaign_to_resp(row)

    async def assign_to_user(
        self, user_id: str, payload: AssignBenefitRequest
    ) -> UserBenefitGrantResponse:
        """运营手动「增加授予」。默认授予活动不可再次手动发放。"""
        uid = parse_int_id(user_id)
        cid = parse_int_id(payload.campaign_id)
        if not uid or not cid:
            raise ValueError("用户或活动无效")

        async with mysql_session() as session:
            async with session.begin():
                user = await session.get(UserORM, uid)
                camp = await session.get(BenefitCampaignORM, cid)
                if not user or user.user_type != "mp_user":
                    raise ValueError("用户不存在")
                if not camp:
                    raise ValueError("活动不存在")
                if camp.status not in ("active", "paused"):
                    raise ValueError("活动未启用，无法发放")

                grant_mode = getattr(camp, "grant_mode", None) or "addon"
                if grant_mode == "default":
                    raise ValueError("默认授予权益由系统自动发放，不能再次手动授予")
                if grant_mode != "addon":
                    raise ValueError("仅「增加授予」类活动可手动发放")

                # membership 范围的增加授予：校验用户等级匹配
                if camp.grant_scope == "membership":
                    if not camp.membership_level_id or user.membership_level_id != camp.membership_level_id:
                        raise ValueError("该权益仅可授予对应会员等级用户")

                now = now_tz()
                # 每次增加授予使用独立 cycle_key，可多次叠加发放
                cycle_key = f"addon-{now.strftime('%Y%m%d%H%M%S%f')}"
                report_q = payload.report_quota if payload.report_quota is not None else camp.report_quota
                ask_q = payload.ask_quota if payload.ask_quota is not None else camp.ask_quota
                push_q = payload.push_quota if payload.push_quota is not None else camp.push_quota
                valid_from = payload.valid_from or camp.start_at or now
                valid_to = payload.valid_to or camp.end_at

                row = UserBenefitGrantORM(
                    user_id=uid,
                    campaign_id=cid,
                    source="manual",
                    cycle_key=cycle_key,
                    report_limit=report_q,
                    ask_limit=ask_q,
                    push_limit=push_q,
                    report_used=0,
                    ask_used=0,
                    push_used=0,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    status="active",
                    remark=payload.remark or "运营增加授予",
                )
                session.add(row)
                await session.flush()
                await session.refresh(row)
                return _grant_to_resp(row, camp)

    async def revoke_grant(self, grant_id: str) -> bool:
        gid = parse_int_id(grant_id)
        if not gid:
            return False
        async with mysql_session() as session:
            async with session.begin():
                row = await session.get(UserBenefitGrantORM, gid)
                if not row:
                    return False
                row.status = "revoked"
                row.updated_at = now_tz()
                return True

    async def list_user_grants(
        self, user_id: str, *, include_inactive: bool = False
    ) -> List[UserBenefitGrantResponse]:
        uid = parse_int_id(user_id)
        if not uid:
            return []
        async with get_mysql_session() as session:
            q = (
                select(UserBenefitGrantORM, BenefitCampaignORM)
                .join(BenefitCampaignORM, BenefitCampaignORM.id == UserBenefitGrantORM.campaign_id)
                .where(UserBenefitGrantORM.user_id == uid)
                .order_by(UserBenefitGrantORM.id.desc())
            )
            if not include_inactive:
                q = q.where(UserBenefitGrantORM.status == "active")
            rows = (await session.execute(q)).all()
            now = now_tz()
            out = []
            for grant, camp in rows:
                resp = _grant_to_resp(grant, camp)
                valid_to = self._as_aware(grant.valid_to, now)
                if grant.status == "active" and valid_to and now > valid_to:
                    resp.status = "expired"
                out.append(resp)
            return out

    async def ensure_auto_grants(self, user_id: str) -> None:
        """为用户补齐当前周期的「默认授予」活动权益（membership/all）。增加授予不自动发。"""
        try:
            await self._ensure_auto_grants_impl(user_id, default_mode_only=True)
        except Exception as e:
            err = str(e).lower()
            if "grant_mode" in err or "unknown column" in err:
                logger.warning(f"grant_mode 不可用，回退旧自动发放逻辑: {e}")
                await self._ensure_auto_grants_impl(user_id, default_mode_only=False)
            else:
                raise

    async def _ensure_auto_grants_impl(self, user_id: str, *, default_mode_only: bool) -> None:
        uid = parse_int_id(user_id)
        if not uid:
            return
        now = now_tz()
        async with mysql_session() as session:
            async with session.begin():
                user = await session.get(UserORM, uid)
                if not user or user.user_type != "mp_user":
                    return

                conds = [
                    BenefitCampaignORM.status == "active",
                    BenefitCampaignORM.grant_scope.in_(["all", "membership"]),
                ]
                if default_mode_only:
                    conds.append(BenefitCampaignORM.grant_mode == "default")
                camps = (
                    await session.execute(select(BenefitCampaignORM).where(*conds))
                ).scalars().all()

                for camp in camps:
                    if not self._campaign_window_ok(camp, now):
                        continue
                    if camp.grant_scope == "membership":
                        if not camp.membership_level_id or user.membership_level_id != camp.membership_level_id:
                            continue
                    cycle_key = self._cycle_key(camp.cycle_type, now)
                    existing = await session.execute(
                        select(UserBenefitGrantORM).where(
                            UserBenefitGrantORM.user_id == uid,
                            UserBenefitGrantORM.campaign_id == camp.id,
                            UserBenefitGrantORM.cycle_key == cycle_key,
                        )
                    )
                    if existing.scalar_one_or_none():
                        continue

                    if camp.cycle_type == "once":
                        hist = await session.execute(
                            select(UserBenefitGrantORM.id).where(
                                UserBenefitGrantORM.user_id == uid,
                                UserBenefitGrantORM.campaign_id == camp.id,
                                UserBenefitGrantORM.cycle_key == "once",
                            ).limit(1)
                        )
                        if hist.scalar_one_or_none():
                            continue

                    source = "all_auto" if camp.grant_scope == "all" else "membership_auto"
                    valid_to = camp.end_at
                    if camp.cycle_type == "daily":
                        valid_to = datetime(now.year, now.month, now.day, 23, 59, 59, tzinfo=now.tzinfo)
                    elif camp.cycle_type == "monthly":
                        if now.month == 12:
                            nxt = datetime(now.year + 1, 1, 1, tzinfo=now.tzinfo)
                        else:
                            nxt = datetime(now.year, now.month + 1, 1, tzinfo=now.tzinfo)
                        valid_to = nxt - timedelta(seconds=1)
                        if camp.end_at and (not valid_to or valid_to > camp.end_at):
                            valid_to = camp.end_at

                    session.add(
                        UserBenefitGrantORM(
                            user_id=uid,
                            campaign_id=camp.id,
                            source=source,
                            cycle_key=cycle_key,
                            report_limit=camp.report_quota or 0,
                            ask_limit=camp.ask_quota or 0,
                            push_limit=camp.push_quota or 0,
                            report_used=0,
                            ask_used=0,
                            push_used=0,
                            valid_from=camp.start_at or now,
                            valid_to=valid_to,
                            status="active",
                            remark="系统默认授予",
                        )
                    )

    async def get_active_grants_for_user(
        self, session, user_id: int, now: Optional[datetime] = None
    ) -> List[tuple]:
        """返回 (grant, campaign) 列表，按 priority、valid_to 排序。可叠加时全部返回；不可叠加只取优先。"""
        now = now or now_tz()
        rows = (
            await session.execute(
                select(UserBenefitGrantORM, BenefitCampaignORM)
                .join(BenefitCampaignORM, BenefitCampaignORM.id == UserBenefitGrantORM.campaign_id)
                .where(
                    UserBenefitGrantORM.user_id == user_id,
                    UserBenefitGrantORM.status == "active",
                )
                .order_by(BenefitCampaignORM.priority.asc(), UserBenefitGrantORM.id.asc())
            )
        ).all()

        active = []
        for grant, camp in rows:
            if not self._grant_valid(grant, now):
                continue
            if not self._campaign_window_ok(camp, now) and camp.status != "active":
                continue
            active.append((grant, camp))

        # 不可叠加：只保留 priority 最高（数值最小）的一条
        stackable = [x for x in active if x[1].stackable]
        non_stack = [x for x in active if not x[1].stackable]
        result = list(stackable)
        if non_stack:
            result.append(non_stack[0])
        # 扣减顺序：先到期先用，再 priority
        result.sort(
            key=lambda x: (
                self._as_aware(x[0].valid_to, now) or datetime.max.replace(tzinfo=now.tzinfo),
                x[1].priority or 100,
                x[0].id,
            )
        )
        return result

    async def sum_remaining(self, user_id: str, kind: BenefitKind) -> int:
        await self.ensure_auto_grants(user_id)
        uid = parse_int_id(user_id)
        if not uid:
            return 0
        now = now_tz()
        async with get_mysql_session() as session:
            pairs = await self.get_active_grants_for_user(session, uid, now)
            return sum(self._kind_remaining(g, kind) for g, _ in pairs)

    async def summarize_user_benefits(self, user_id: str) -> dict:
        try:
            await self.ensure_auto_grants(user_id)
        except Exception as e:
            logger.warning(f"自动发放权益失败（继续汇总已有额度）: {e}")
        grants = await self.list_user_grants(user_id, include_inactive=False)
        now = now_tz()
        active = [
            g
            for g in grants
            if g.status == "active"
            and (not g.valid_to or self._as_aware(g.valid_to, now) >= now)
        ]
        return {
            "grants": [g.model_dump() for g in active],
            "report_benefit_remaining": sum(g.report_remaining for g in active),
            "ask_benefit_remaining": sum(g.ask_remaining for g in active),
            "push_benefit_remaining": sum(g.push_remaining for g in active),
        }

    async def consume(
        self,
        session,
        user_id: int,
        kind: BenefitKind,
        *,
        now: Optional[datetime] = None,
    ) -> Optional[UserBenefitGrantORM]:
        """在已有事务 session 中扣减 1 次活动权益，成功返回 grant，否则 None。"""
        now = now or now_tz()
        pairs = await self.get_active_grants_for_user(session, user_id, now)
        for grant, _camp in pairs:
            if self._kind_remaining(grant, kind) <= 0:
                continue
            # 行锁
            locked = await session.execute(
                select(UserBenefitGrantORM)
                .where(UserBenefitGrantORM.id == grant.id)
                .with_for_update()
            )
            row = locked.scalar_one_or_none()
            if not row or not self._grant_valid(row, now):
                continue
            if self._kind_remaining(row, kind) <= 0:
                continue
            if kind == "ask":
                row.ask_used += 1
            elif kind == "push":
                row.push_used += 1
            else:
                row.report_used += 1
            row.updated_at = now
            # 若三类都用尽则标记 exhausted
            if (
                row.report_used >= row.report_limit
                and row.ask_used >= row.ask_limit
                and row.push_used >= row.push_limit
            ):
                row.status = "exhausted"
            return row
        return None


benefit_service = BenefitService()


# 各会员等级默认权益（来源：data/会员等级与费用明细.xlsx）
# push_quota = AI深度分析；权益优先消耗，用尽后按等级单价扣款
DEFAULT_LEVEL_CAMPAIGNS = [
    {
        "code": "level_trial_monthly",
        "name": "体验会员·每月权益",
        "description": "体验会员每月刷新：研报3次、问股5次、AI深度分析2次",
        "level_code": "trial",
        "cycle_type": "monthly",
        "report_quota": 3,
        "ask_quota": 5,
        "push_quota": 2,
        "priority": 100,
    },
    {
        "code": "level_silver_welcome",
        "name": "银卡会员·入门权益",
        "description": "银卡一次性权益：研报10次、问股20次、AI深度分析5次",
        "level_code": "silver",
        "cycle_type": "once",
        "report_quota": 10,
        "ask_quota": 20,
        "push_quota": 5,
        "priority": 90,
    },
    {
        "code": "level_silver_monthly",
        "name": "银卡会员·每月权益",
        "description": "银卡每月刷新：研报3次、问股20次、AI深度分析10次",
        "level_code": "silver",
        "cycle_type": "monthly",
        "report_quota": 3,
        "ask_quota": 20,
        "push_quota": 10,
        "priority": 80,
    },
    {
        "code": "level_gold_welcome",
        "name": "金卡会员·入门权益",
        "description": "金卡一次性权益：研报15次、问股30次、AI深度分析10次",
        "level_code": "gold",
        "cycle_type": "once",
        "report_quota": 15,
        "ask_quota": 30,
        "push_quota": 10,
        "priority": 70,
    },
    {
        "code": "level_gold_monthly",
        "name": "金卡会员·每月权益",
        "description": "金卡每月刷新：研报10次、问股30次、AI深度分析20次",
        "level_code": "gold",
        "cycle_type": "monthly",
        "report_quota": 10,
        "ask_quota": 30,
        "push_quota": 20,
        "priority": 60,
    },
    {
        "code": "level_platinum_welcome",
        "name": "白金会员·入门权益",
        "description": "白金一次性权益：研报15次、问股30次、AI深度分析10次",
        "level_code": "platinum",
        "cycle_type": "once",
        "report_quota": 15,
        "ask_quota": 30,
        "push_quota": 10,
        "priority": 55,
    },
    {
        "code": "level_platinum_monthly",
        "name": "白金会员·每月权益",
        "description": "白金每月刷新：研报5次、问股20次、AI深度分析8次",
        "level_code": "platinum",
        "cycle_type": "monthly",
        "report_quota": 5,
        "ask_quota": 20,
        "push_quota": 8,
        "priority": 50,
    },
    {
        "code": "level_diamond_welcome",
        "name": "钻石会员·入门权益",
        "description": "钻石一次性权益：研报30次、问股60次、AI深度分析20次",
        "level_code": "diamond",
        "cycle_type": "once",
        "report_quota": 30,
        "ask_quota": 60,
        "push_quota": 20,
        "priority": 45,
    },
    {
        "code": "level_diamond_monthly",
        "name": "钻石会员·每月权益",
        "description": "钻石每月刷新：研报30次、问股60次、AI深度分析50次",
        "level_code": "diamond",
        "cycle_type": "monthly",
        "report_quota": 30,
        "ask_quota": 60,
        "push_quota": 50,
        "priority": 40,
    },
    {
        "code": "level_supreme_welcome",
        "name": "至尊会员·入门权益",
        "description": "至尊一次性权益：研报100次、问股200次、AI深度分析50次",
        "level_code": "supreme",
        "cycle_type": "once",
        "report_quota": 100,
        "ask_quota": 200,
        "push_quota": 50,
        "priority": 35,
    },
    {
        "code": "level_supreme_monthly",
        "name": "至尊会员·每月权益",
        "description": "至尊每月刷新：研报不限、问股1000次、AI深度分析150次",
        "level_code": "supreme",
        "cycle_type": "monthly",
        "report_quota": 99999,
        "ask_quota": 1000,
        "push_quota": 150,
        "priority": 30,
    },
]

DEPRECATED_LEVEL_CAMPAIGN_CODES = {
    "level_normal_welcome",
    "level_vip_welcome",
    "level_vip_monthly",
}

DEFAULT_LEVEL_CAMPAIGN_CODES = {c["code"] for c in DEFAULT_LEVEL_CAMPAIGNS}


async def _sync_campaign_grants(session, campaign_id: int, cfg: dict) -> None:
    """同步已发放默认权益的上限（不削减已使用量）。"""
    grants = (
        await session.execute(
            select(UserBenefitGrantORM).where(
                UserBenefitGrantORM.campaign_id == campaign_id,
                UserBenefitGrantORM.status == "active",
            )
        )
    ).scalars().all()
    now = now_tz()
    for g in grants:
        g.report_limit = max(int(g.report_used or 0), int(cfg["report_quota"]))
        g.ask_limit = max(int(g.ask_used or 0), int(cfg["ask_quota"]))
        g.push_limit = max(int(g.push_used or 0), int(cfg["push_quota"]))
        g.updated_at = now
        if (
            g.report_used >= g.report_limit
            and g.ask_used >= g.ask_limit
            and g.push_used >= g.push_limit
        ):
            g.status = "exhausted"


async def get_level_benefit_templates() -> dict[str, dict]:
    """按等级 code 汇总默认权益模板（供会员列表展示）。"""
    by_level: dict[str, dict] = {}
    for cfg in DEFAULT_LEVEL_CAMPAIGNS:
        code = cfg["level_code"]
        bucket = by_level.setdefault(
            code,
            {
                "monthly_report": 0,
                "monthly_ask": 0,
                "monthly_push": 0,
                "once_report": 0,
                "once_ask": 0,
                "once_push": 0,
            },
        )
        if cfg["cycle_type"] == "monthly":
            bucket["monthly_report"] += cfg["report_quota"]
            bucket["monthly_ask"] += cfg["ask_quota"]
            bucket["monthly_push"] += cfg["push_quota"]
        else:
            bucket["once_report"] += cfg["report_quota"]
            bucket["once_ask"] += cfg["ask_quota"]
            bucket["once_push"] += cfg["push_quota"]
    return by_level


async def init_default_level_campaigns() -> None:
    """为各会员等级写入默认权益活动（幂等）。"""
    from app.models.sql.models import MembershipLevelORM

    async with get_mysql_session() as session:
        level_map = {}
        rows = (await session.execute(select(MembershipLevelORM))).scalars().all()
        for r in rows:
            level_map[r.code] = r.id

        created = 0
        now = now_tz()
        for cfg in DEFAULT_LEVEL_CAMPAIGNS:
            level_id = level_map.get(cfg["level_code"])
            if not level_id:
                logger.warning(f"跳过权益 {cfg['code']}：缺少会员等级 {cfg['level_code']}")
                continue
            exists = await session.execute(
                select(BenefitCampaignORM).where(BenefitCampaignORM.code == cfg["code"])
            )
            row = exists.scalar_one_or_none()
            if row:
                row.name = cfg["name"]
                row.description = cfg["description"]
                row.grant_mode = "default"
                row.grant_scope = "membership"
                row.membership_level_id = level_id
                row.cycle_type = cfg["cycle_type"]
                row.report_quota = cfg["report_quota"]
                row.ask_quota = cfg["ask_quota"]
                row.push_quota = cfg["push_quota"]
                row.priority = cfg["priority"]
                row.stackable = True
                if row.status in ("draft", "paused", "ended"):
                    row.status = "active"
                row.updated_at = now
                await _sync_campaign_grants(session, row.id, cfg)
                continue

            session.add(
                BenefitCampaignORM(
                    name=cfg["name"],
                    code=cfg["code"],
                    description=cfg["description"],
                    status="active",
                    grant_scope="membership",
                    grant_mode="default",
                    membership_level_id=level_id,
                    cycle_type=cfg["cycle_type"],
                    start_at=None,
                    end_at=None,
                    report_quota=cfg["report_quota"],
                    ask_quota=cfg["ask_quota"],
                    push_quota=cfg["push_quota"],
                    stackable=True,
                    priority=cfg["priority"],
                )
            )
            created += 1

        deprecated = (
            await session.execute(
                select(BenefitCampaignORM).where(
                    BenefitCampaignORM.code.in_(DEPRECATED_LEVEL_CAMPAIGN_CODES)
                )
            )
        ).scalars().all()
        for row in deprecated:
            row.status = "ended"
            row.updated_at = now

        if created:
            logger.info(f"✅ 已初始化 {created} 条会员等级默认权益活动")
        else:
            logger.info("✅ 会员等级默认权益活动已就绪")
