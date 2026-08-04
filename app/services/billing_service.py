"""计费服务 - 会员月费、问股/研报分开扣费（MySQL）"""

from decimal import Decimal
from typing import List, Literal, Optional, Tuple

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mysql_db import get_mysql_session, mysql_session, parse_int_id
from app.models.billing import (
    BillingActionType,
    BillingRecord,
    BillingRecordResponse,
    ChargeResult,
)
from app.models.membership import MembershipLevel
from app.models.sql.converters import billing_to_response
from app.models.sql.models import BillingRecordORM, UserORM, UserQuotaUsageORM
from app.services.membership_service import membership_service
from app.utils.timezone import now_tz

try:
    from tradingagents.utils.logging_manager import get_logger
except ImportError:
    import logging

    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)

logger = get_logger("billing_service")

UsageKind = Literal["report", "ask"]


def _benefit_service():
    from app.services.benefit_service import benefit_service
    return benefit_service


class InsufficientBalanceError(Exception):
    """余额不足"""

    def __init__(self, required: Decimal, balance: Decimal):
        self.required = required
        self.balance = balance
        super().__init__(f"余额不足，需要 {required} 元，当前余额 {balance} 元")


class BillingService:
    @staticmethod
    def _current_period() -> str:
        return now_tz().strftime("%Y-%m")

    @staticmethod
    def _monthly_fee(level: MembershipLevel) -> Decimal:
        return Decimal(str(level.monthly_price or 0))

    async def _get_user_level(self, user: UserORM) -> Optional[MembershipLevel]:
        if user.membership_level_id:
            level = await membership_service.get_level_by_id(str(user.membership_level_id))
            if level:
                return level
        return await membership_service.get_default_level()

    async def _get_quota_row(
        self, session: AsyncSession, user_id: int, period: str
    ) -> Optional[UserQuotaUsageORM]:
        result = await session.execute(
            select(UserQuotaUsageORM).where(
                UserQuotaUsageORM.user_id == user_id,
                UserQuotaUsageORM.period == period,
            )
        )
        return result.scalar_one_or_none()

    async def _ensure_quota_row(
        self, session: AsyncSession, user_id: int, period: str
    ) -> UserQuotaUsageORM:
        usage = await self._get_quota_row(session, user_id, period)
        if usage:
            return usage
        usage = UserQuotaUsageORM(
            user_id=user_id,
            period=period,
            free_generations_used=0,
            free_asks_used=0,
            membership_fee_charged=False,
            updated_at=now_tz(),
        )
        session.add(usage)
        await session.flush()
        return usage

    async def get_quota_usage(self, user_id: str) -> dict:
        """返回额度：剩余免费次数以活动权益为准（权益优先，无权益则单次扣款）。"""
        uid = parse_int_id(user_id)
        if not uid:
            return {
                "report_used": 0,
                "report_limit": 0,
                "ask_used": 0,
                "ask_limit": 0,
            }
        period = self._current_period()
        fee_charged = True
        monthly_fee = Decimal("0")
        try:
            async with get_mysql_session() as session:
                usage = await self._get_quota_row(session, uid, period)
                user = await session.get(UserORM, uid)
                if not user:
                    return {
                        "report_used": 0,
                        "report_limit": 0,
                        "ask_used": 0,
                        "ask_limit": 0,
                    }
                level = await self._get_user_level(user)
                fee_charged = usage.membership_fee_charged if usage else False
                monthly_fee = self._monthly_fee(level) if level else Decimal("0")
        except Exception as e:
            logger.exception("读取会员额度行失败: %s", e)

        report_benefit = ask_benefit = push_benefit = 0
        grants: list = []
        try:
            benefits = await _benefit_service().summarize_user_benefits(user_id)
            report_benefit = int(benefits.get("report_benefit_remaining") or 0)
            ask_benefit = int(benefits.get("ask_benefit_remaining") or 0)
            push_benefit = int(benefits.get("push_benefit_remaining") or 0)
            grants = benefits.get("grants") or []
        except Exception as e:
            logger.exception("汇总活动权益失败: %s", e)

        report_limit = sum(int(g.get("report_limit") or 0) for g in grants)
        ask_limit = sum(int(g.get("ask_limit") or 0) for g in grants)
        report_used = sum(int(g.get("report_used") or 0) for g in grants)
        ask_used = sum(int(g.get("ask_used") or 0) for g in grants)

        return {
            "report_used": report_used,
            "report_limit": report_limit,
            "report_remaining": report_benefit,
            "report_membership_remaining": 0,
            "report_benefit_remaining": report_benefit,
            "ask_used": ask_used,
            "ask_limit": ask_limit,
            "ask_remaining": ask_benefit,
            "ask_membership_remaining": 0,
            "ask_benefit_remaining": ask_benefit,
            "push_benefit_remaining": push_benefit,
            "benefit_grants": grants,
            "membership_fee_charged": fee_charged or monthly_fee <= 0,
            "monthly_fee": float(monthly_fee),
        }

    async def ensure_monthly_fee(self, user_id: str) -> dict:
        """尝试扣除当月会员费（每个自然月仅扣一次）"""
        uid = parse_int_id(user_id)
        if not uid:
            return {"success": False, "reason": "用户不存在"}

        period = self._current_period()
        async with mysql_session() as session:
            async with session.begin():
                result = await session.execute(
                    select(UserORM).where(UserORM.id == uid).with_for_update()
                )
                user = result.scalar_one_or_none()
                if not user:
                    return {"success": False, "reason": "用户不存在"}

                level = await self._get_user_level(user)
                if not level:
                    return {"success": False, "reason": "会员等级配置异常"}

                monthly_fee = self._monthly_fee(level)
                usage = await self._ensure_quota_row(session, uid, period)
                balance = Decimal(str(user.balance))

                if monthly_fee <= 0:
                    usage.membership_fee_charged = True
                    usage.updated_at = now_tz()
                    return {
                        "success": True,
                        "charged": False,
                        "amount": 0.0,
                        "balance": float(balance),
                        "membership_fee_paid": True,
                    }

                if usage.membership_fee_charged:
                    return {
                        "success": True,
                        "charged": False,
                        "amount": 0.0,
                        "balance": float(balance),
                        "membership_fee_paid": True,
                    }

                if balance < monthly_fee:
                    return {
                        "success": False,
                        "charged": False,
                        "amount": float(monthly_fee),
                        "balance": float(balance),
                        "membership_fee_paid": False,
                        "reason": f"本月会员费 {monthly_fee} 元未扣除，余额不足，请先充值",
                    }

                user.balance = balance - monthly_fee
                user.updated_at = now_tz()
                balance_after = Decimal(str(user.balance))
                usage.membership_fee_charged = True
                usage.updated_at = now_tz()
                self._create_record_in_session(
                    session,
                    user_id=uid,
                    action_type=BillingActionType.MEMBERSHIP_FEE,
                    amount=-monthly_fee,
                    balance_before=balance,
                    balance_after=balance_after,
                    is_free=False,
                    level=level,
                    remark=f"{level.name} 月会员费 {monthly_fee} 元",
                )
                logger.info("用户 %s 已扣除月会员费 %s 元", user_id, monthly_fee)
                return {
                    "success": True,
                    "charged": True,
                    "amount": float(monthly_fee),
                    "balance": float(balance_after),
                    "membership_fee_paid": True,
                }

    def _usage_limits(
        self, level: MembershipLevel, kind: UsageKind
    ) -> Tuple[int, Decimal]:
        if kind == "ask":
            return level.monthly_free_asks, Decimal(str(level.per_ask_price))
        return level.monthly_free_generations, Decimal(str(level.per_generation_price))

    def _usage_used(self, usage: Optional[UserQuotaUsageORM], kind: UsageKind) -> int:
        if not usage:
            return 0
        if kind == "ask":
            return usage.free_asks_used
        return usage.free_generations_used

    async def check_can_use(self, user_id: str, kind: UsageKind = "report") -> dict:
        uid = parse_int_id(user_id)
        if not uid:
            return {"can_use": False, "reason": "用户不存在"}

        fee_result = await self.ensure_monthly_fee(user_id)
        if not fee_result.get("membership_fee_paid"):
            return {
                "can_use": False,
                "can_generate": False,
                "reason": fee_result.get("reason", "本月会员费未扣除"),
                "price": fee_result.get("amount", 0),
                "balance": fee_result.get("balance", 0),
                "membership_fee_paid": False,
            }

        # 账单逻辑：权益优先；无可用权益再按等级单价单次扣款
        benefit_remaining = await _benefit_service().sum_remaining(user_id, kind)

        async with get_mysql_session() as session:
            user = await session.get(UserORM, uid)
            if not user:
                return {"can_use": False, "can_generate": False, "reason": "用户不存在"}
            level = await self._get_user_level(user)
            _, price = self._usage_limits(level, kind) if level else (0, Decimal("9.90"))
            free_remaining = benefit_remaining
            balance = Decimal(str(user.balance))
            level_name = level.name if level else "普通会员"

            base = {
                "membership_fee_paid": True,
                "membership_level_name": level_name,
                "balance": float(balance),
                "monthly_fee": float(self._monthly_fee(level)) if level else 0.0,
                "benefit_remaining": benefit_remaining,
                "membership_remaining": 0,
            }
            if kind == "report":
                base.update(
                    {
                        "report_free_remaining": free_remaining,
                        "report_price": float(price),
                    }
                )
            else:
                base.update(
                    {
                        "ask_free_remaining": free_remaining,
                        "ask_price": float(price),
                    }
                )

            if free_remaining > 0:
                return {
                    **base,
                    "can_use": True,
                    "can_generate": True,
                    "is_free": True,
                    "price": float(price),
                    "free_remaining": free_remaining,
                }
            if balance >= price:
                return {
                    **base,
                    "can_use": True,
                    "can_generate": True,
                    "is_free": False,
                    "price": float(price),
                    "free_remaining": 0,
                }
            return {
                **base,
                "can_use": False,
                "can_generate": False,
                "is_free": False,
                "price": float(price),
                "free_remaining": 0,
                "reason": "余额不足，请先充值",
            }

    async def check_can_generate(self, user_id: str) -> dict:
        return await self.check_can_use(user_id, "report")

    async def check_can_ask(self, user_id: str) -> dict:
        return await self.check_can_use(user_id, "ask")

    async def _charge_for_usage(
        self,
        user_id: str,
        kind: UsageKind,
        *,
        stock_code: Optional[str],
        ref_id: str,
        free_remark: str,
        paid_remark: str,
    ) -> ChargeResult:
        uid = parse_int_id(user_id)
        if not uid:
            return ChargeResult(success=False, message="用户不存在")

        fee_result = await self.ensure_monthly_fee(user_id)
        if not fee_result.get("membership_fee_paid"):
            return ChargeResult(
                success=False,
                message=fee_result.get("reason", "本月会员费未扣除"),
            )

        action_type = BillingActionType.GENERATE if kind == "report" else BillingActionType.ASK
        await _benefit_service().ensure_auto_grants(user_id)

        async with mysql_session() as session:
            async with session.begin():
                result = await session.execute(
                    select(UserORM).where(UserORM.id == uid).with_for_update()
                )
                user = result.scalar_one_or_none()
                if not user:
                    return ChargeResult(success=False, message="用户不存在")

                level = await self._get_user_level(user)
                if not level:
                    return ChargeResult(success=False, message="会员等级配置异常")

                _limit, price = self._usage_limits(level, kind)
                balance = Decimal(str(user.balance))

                # 账单逻辑：1) 权益优先  2) 无可用权益则按等级单价单次扣款
                consumed = await _benefit_service().consume(session, uid, kind)
                if consumed:
                    from app.models.sql.models import BenefitCampaignORM
                    camp = await session.get(BenefitCampaignORM, consumed.campaign_id)
                    camp_name = camp.name if camp else str(consumed.campaign_id)
                    record = self._create_record_in_session(
                        session,
                        user_id=uid,
                        action_type=action_type,
                        amount=Decimal("0"),
                        balance_before=balance,
                        balance_after=balance,
                        is_free=True,
                        stock_code=stock_code,
                        task_id=ref_id,
                        level=level,
                        remark=f"{free_remark}（活动权益:{camp_name}）",
                    )
                    await session.flush()
                    return ChargeResult(
                        success=True,
                        is_free=True,
                        amount=Decimal("0"),
                        balance_after=balance,
                        billing_record_id=str(record.id),
                        message=f"已使用活动权益「{camp_name}」",
                    )

                # 无可用权益 → 单次扣款
                if balance < price:
                    raise InsufficientBalanceError(price, balance)

                user.balance = balance - price
                user.updated_at = now_tz()
                balance_after = Decimal(str(user.balance))
                record = self._create_record_in_session(
                    session,
                    user_id=uid,
                    action_type=action_type,
                    amount=-price,
                    balance_before=balance,
                    balance_after=balance_after,
                    is_free=False,
                    stock_code=stock_code,
                    task_id=ref_id,
                    level=level,
                    remark=paid_remark,
                )
                await session.flush()
                return ChargeResult(
                    success=True,
                    is_free=False,
                    amount=price,
                    balance_after=balance_after,
                    billing_record_id=str(record.id),
                    message=f"已扣费 {price} 元",
                )

    async def charge_for_generation(
        self,
        user_id: str,
        stock_code: str,
        task_id: str,
    ) -> ChargeResult:
        return await self._charge_for_usage(
            user_id,
            "report",
            stock_code=stock_code,
            ref_id=task_id,
            free_remark=f"免费额度生成研报 {stock_code}",
            paid_remark=f"付费生成研报 {stock_code}",
        )

    async def charge_for_ask(
        self,
        user_id: str,
        stock_code: Optional[str],
        session_id: str,
    ) -> ChargeResult:
        code_label = stock_code or "问股"
        return await self._charge_for_usage(
            user_id,
            "ask",
            stock_code=stock_code,
            ref_id=session_id,
            free_remark=f"免费额度问股 {code_label}",
            paid_remark=f"付费问股 {code_label}",
        )

    async def add_balance(
        self,
        user_id: str,
        amount: Decimal,
        action_type: BillingActionType,
        order_no: Optional[str] = None,
        remark: str = "",
    ) -> BillingRecord:
        uid = parse_int_id(user_id)
        if not uid:
            raise ValueError("用户不存在")
        async with mysql_session() as session:
            async with session.begin():
                result = await session.execute(
                    select(UserORM).where(UserORM.id == uid).with_for_update()
                )
                user = result.scalar_one_or_none()
                if not user:
                    raise ValueError("用户不存在")
                balance_before = Decimal(str(user.balance))
                user.balance = balance_before + amount
                user.updated_at = now_tz()
                balance_after = Decimal(str(user.balance))
                record = self._create_record_in_session(
                    session,
                    user_id=uid,
                    action_type=action_type,
                    amount=amount,
                    balance_before=balance_before,
                    balance_after=balance_after,
                    is_free=False,
                    order_no=order_no,
                    remark=remark or f"充值 {amount} 元",
                )
                await session.flush()
                await session.refresh(record)
                return BillingRecord(
                    id=record.id,
                    user_id=record.user_id,
                    action_type=action_type,
                    amount=amount,
                    balance_before=balance_before,
                    balance_after=balance_after,
                    is_free=False,
                    order_no=order_no,
                    remark=record.remark,
                    created_at=record.created_at or now_tz(),
                )

    async def adjust_balance(
        self,
        user_id: str,
        amount: Decimal,
        remark: str,
        operator: str = "admin",
    ) -> BillingRecord:
        uid = parse_int_id(user_id)
        if not uid:
            raise ValueError("用户不存在")
        async with mysql_session() as session:
            async with session.begin():
                result = await session.execute(
                    select(UserORM).where(UserORM.id == uid).with_for_update()
                )
                user = result.scalar_one_or_none()
                if not user:
                    raise ValueError("用户不存在")
                balance_before = Decimal(str(user.balance))
                balance_after = balance_before + amount
                if balance_after < 0:
                    raise ValueError("调整后余额不能为负")
                user.balance = balance_after
                user.updated_at = now_tz()
                record = self._create_record_in_session(
                    session,
                    user_id=uid,
                    action_type=BillingActionType.ADJUST,
                    amount=amount,
                    balance_before=balance_before,
                    balance_after=balance_after,
                    is_free=False,
                    remark=f"{remark}（操作人: {operator}）",
                )
                await session.flush()
                await session.refresh(record)
                return BillingRecord(
                    id=record.id,
                    user_id=record.user_id,
                    action_type=BillingActionType.ADJUST,
                    amount=amount,
                    balance_before=balance_before,
                    balance_after=balance_after,
                    is_free=False,
                    remark=record.remark,
                    created_at=record.created_at or now_tz(),
                )

    def _create_record_in_session(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        action_type: BillingActionType,
        amount: Decimal,
        balance_before: Decimal,
        balance_after: Decimal,
        is_free: bool = False,
        stock_code: Optional[str] = None,
        task_id: Optional[str] = None,
        report_id: Optional[str] = None,
        order_no: Optional[str] = None,
        level: Optional[MembershipLevel] = None,
        remark: str = "",
    ) -> BillingRecordORM:
        record = BillingRecordORM(
            user_id=user_id,
            action_type=action_type.value,
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            is_free=is_free,
            stock_code=stock_code,
            task_id=task_id,
            report_id=report_id,
            order_no=order_no,
            membership_level_id=level.id if level else None,
            membership_level_name=level.name if level else None,
            remark=remark,
            created_at=now_tz(),
        )
        session.add(record)
        return record

    async def list_records(
        self,
        user_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
        action_type: Optional[str] = None,
    ) -> List[BillingRecordResponse]:
        async with get_mysql_session() as session:
            stmt = select(BillingRecordORM).order_by(BillingRecordORM.created_at.desc())
            if user_id:
                uid = parse_int_id(user_id)
                if uid:
                    stmt = stmt.where(BillingRecordORM.user_id == uid)
            if action_type:
                stmt = stmt.where(BillingRecordORM.action_type == action_type)
            stmt = stmt.offset(skip).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [billing_to_response(r) for r in rows]

    async def count_records(
        self,
        user_id: Optional[str] = None,
        action_type: Optional[str] = None,
    ) -> int:
        async with get_mysql_session() as session:
            stmt = select(func.count(BillingRecordORM.id))
            if user_id:
                uid = parse_int_id(user_id)
                if uid:
                    stmt = stmt.where(BillingRecordORM.user_id == uid)
            if action_type:
                stmt = stmt.where(BillingRecordORM.action_type == action_type)
            return (await session.execute(stmt)).scalar() or 0

    async def get_statistics(self) -> dict:
        async with get_mysql_session() as session:
            gen_stmt = select(
                func.count(BillingRecordORM.id).label("total_generations"),
                func.sum(case((BillingRecordORM.is_free.is_(True), 1), else_=0)).label("free_generations"),
                func.sum(case((BillingRecordORM.is_free.is_(False), 1), else_=0)).label("paid_generations"),
                func.sum(
                    case(
                        (BillingRecordORM.is_free.is_(False), func.abs(BillingRecordORM.amount)),
                        else_=0,
                    )
                ).label("total_revenue"),
            ).where(BillingRecordORM.action_type == BillingActionType.GENERATE.value)
            gen_row = (await session.execute(gen_stmt)).one()

            ask_stmt = select(
                func.count(BillingRecordORM.id).label("total_asks"),
                func.sum(
                    case(
                        (BillingRecordORM.is_free.is_(False), func.abs(BillingRecordORM.amount)),
                        else_=0,
                    )
                ).label("ask_revenue"),
            ).where(BillingRecordORM.action_type == BillingActionType.ASK.value)
            ask_row = (await session.execute(ask_stmt)).one()

            fee_stmt = select(
                func.count(BillingRecordORM.id).label("fee_count"),
                func.sum(func.abs(BillingRecordORM.amount)).label("fee_revenue"),
            ).where(BillingRecordORM.action_type == BillingActionType.MEMBERSHIP_FEE.value)
            fee_row = (await session.execute(fee_stmt)).one()

            recharge_stmt = select(
                func.sum(BillingRecordORM.amount).label("total_recharge"),
                func.count(BillingRecordORM.id).label("count"),
            ).where(BillingRecordORM.action_type == BillingActionType.RECHARGE.value)
            recharge_row = (await session.execute(recharge_stmt)).one()

            mp_count_stmt = select(func.count(UserORM.id)).where(
                UserORM.user_type == "mp_user",
                UserORM.is_active.is_(True),
            )
            mp_users = (await session.execute(mp_count_stmt)).scalar() or 0

            return {
                "mp_user_count": mp_users,
                "total_generations": int(gen_row.total_generations or 0),
                "free_generations": int(gen_row.free_generations or 0),
                "paid_generations": int(gen_row.paid_generations or 0),
                "generation_revenue": round(float(gen_row.total_revenue or 0), 2),
                "total_asks": int(ask_row.total_asks or 0),
                "ask_revenue": round(float(ask_row.ask_revenue or 0), 2),
                "membership_fee_count": int(fee_row.fee_count or 0),
                "membership_fee_revenue": round(float(fee_row.fee_revenue or 0), 2),
                "total_recharge": round(float(recharge_row.total_recharge or 0), 2),
                "recharge_count": int(recharge_row.count or 0),
            }


billing_service = BillingService()
