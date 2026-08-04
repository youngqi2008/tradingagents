"""ORM 与 Pydantic 模型转换"""

from decimal import Decimal
from typing import Any, Optional

from app.models.billing import BillingActionType, BillingRecord, BillingRecordResponse
from app.models.membership import MembershipLevel, MembershipLevelResponse
from app.models.role import DEFAULT_MP_ROLE, role_display_name
from app.models.sql.models import BillingRecordORM, MembershipLevelORM, PaymentOrderORM, UserORM
from app.models.user import FavoriteStock, User, UserPreferences, UserResponse
from app.models.payment import PaymentOrderResponse
from app.utils.timezone import now_tz


def _role_name_map():
    try:
        from app.services.role_service import role_service

        return role_service.get_name_map()
    except Exception:
        return None


DEFAULT_PREFERENCES: dict[str, Any] = {
    "default_market": "A股",
    "default_depth": "3",
    "default_analysts": ["市场分析师", "基本面分析师"],
    "auto_refresh": True,
    "refresh_interval": 30,
    "ui_theme": "light",
    "sidebar_width": 240,
    "language": "zh-CN",
    "notifications_enabled": True,
    "email_notifications": False,
    "desktop_notifications": True,
    "analysis_complete_notification": True,
    "system_maintenance_notification": True,
}


def user_orm_to_pydantic(row: UserORM) -> User:
    prefs_data = row.preferences or DEFAULT_PREFERENCES
    favorites_data = row.favorite_stocks or []
    role = getattr(row, "role", None) or DEFAULT_MP_ROLE
    return User(
        id=row.id,
        username=row.username,
        email=row.email,
        hashed_password=row.hashed_password,
        is_active=row.is_active,
        is_verified=row.is_verified,
        is_admin=row.is_admin,
        created_at=row.created_at or now_tz(),
        updated_at=row.updated_at or now_tz(),
        last_login=row.last_login,
        preferences=UserPreferences(**prefs_data),
        daily_quota=row.daily_quota,
        concurrent_limit=row.concurrent_limit,
        total_analyses=row.total_analyses,
        successful_analyses=row.successful_analyses,
        failed_analyses=row.failed_analyses,
        favorite_stocks=[FavoriteStock(**f) for f in favorites_data if isinstance(f, dict)],
        user_type=row.user_type,
        role=role,
        openid=row.openid,
        unionid=row.unionid,
        nickname=row.nickname,
        avatar_url=row.avatar_url,
        phone=row.phone,
        membership_level_id=str(row.membership_level_id) if row.membership_level_id else None,
        balance=Decimal(str(row.balance)),
    )


def user_to_response(user: User) -> UserResponse:
    role = user.role or DEFAULT_MP_ROLE
    return UserResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        is_verified=user.is_verified,
        created_at=user.created_at,
        last_login=user.last_login,
        preferences=user.preferences,
        daily_quota=user.daily_quota,
        concurrent_limit=user.concurrent_limit,
        total_analyses=user.total_analyses,
        successful_analyses=user.successful_analyses,
        failed_analyses=user.failed_analyses,
        user_type=user.user_type,
        role=role,
        role_name=role_display_name(role, _role_name_map()),
        openid=user.openid,
        nickname=user.nickname,
        avatar_url=user.avatar_url,
        phone=user.phone,
        membership_level_id=user.membership_level_id,
        balance=float(user.balance or 0),
    )


def membership_orm_to_pydantic(row: MembershipLevelORM) -> MembershipLevel:
    return MembershipLevel(
        id=row.id,
        name=row.name,
        code=row.code,
        sort_order=row.sort_order,
        monthly_free_generations=row.monthly_free_generations,
        per_generation_price=Decimal(str(row.per_generation_price)),
        monthly_free_asks=row.monthly_free_asks,
        per_ask_price=Decimal(str(row.per_ask_price)),
        monthly_price=Decimal(str(row.monthly_price or 0)),
        description=row.description,
        is_default=row.is_default,
        is_active=row.is_active,
        created_at=row.created_at or now_tz(),
        updated_at=row.updated_at or now_tz(),
    )


def membership_to_response(row: MembershipLevelORM) -> MembershipLevelResponse:
    return MembershipLevelResponse(
        id=str(row.id),
        name=row.name,
        code=row.code,
        sort_order=row.sort_order,
        monthly_free_generations=row.monthly_free_generations,
        per_generation_price=float(row.per_generation_price),
        monthly_free_asks=row.monthly_free_asks,
        per_ask_price=float(row.per_ask_price),
        monthly_price=float(row.monthly_price or 0),
        description=row.description,
        is_default=row.is_default,
        is_active=row.is_active,
        created_at=row.created_at or now_tz(),
        updated_at=row.updated_at or now_tz(),
    )


def billing_orm_to_pydantic(row: BillingRecordORM) -> BillingRecord:
    return BillingRecord(
        id=row.id,
        user_id=row.user_id,
        action_type=BillingActionType(row.action_type),
        amount=Decimal(str(row.amount)),
        balance_before=Decimal(str(row.balance_before)),
        balance_after=Decimal(str(row.balance_after)),
        is_free=row.is_free,
        stock_code=row.stock_code,
        task_id=row.task_id,
        report_id=row.report_id,
        order_no=row.order_no,
        membership_level_id=str(row.membership_level_id) if row.membership_level_id else None,
        membership_level_name=row.membership_level_name,
        remark=row.remark,
        created_at=row.created_at or now_tz(),
    )


def billing_to_response(row: BillingRecordORM) -> BillingRecordResponse:
    return BillingRecordResponse(
        id=str(row.id),
        user_id=str(row.user_id),
        action_type=row.action_type,
        amount=float(row.amount),
        balance_before=float(row.balance_before),
        balance_after=float(row.balance_after),
        is_free=row.is_free,
        stock_code=row.stock_code,
        task_id=row.task_id,
        report_id=row.report_id,
        order_no=row.order_no,
        membership_level_name=row.membership_level_name,
        remark=row.remark,
        created_at=row.created_at or now_tz(),
    )


def payment_to_response(row: PaymentOrderORM) -> PaymentOrderResponse:
    return PaymentOrderResponse(
        id=str(row.id),
        order_no=row.order_no,
        user_id=str(row.user_id),
        amount=float(row.amount),
        status=row.status,
        description=row.description,
        created_at=row.created_at or now_tz(),
        paid_at=row.paid_at,
    )
