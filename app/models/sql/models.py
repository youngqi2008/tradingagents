"""用户与计费模块 MySQL ORM 模型"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    JSON,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class MembershipLevelORM(Base):
    __tablename__ = "membership_levels"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    monthly_free_generations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    per_generation_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("9.90"), nullable=False)
    monthly_free_asks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    per_ask_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("9.90"), nullable=False)
    monthly_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"), nullable=False)
    description: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RoleORM(Base):
    """小程序业务角色（与会员等级、is_admin 独立）"""

    __tablename__ = "mp_roles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UserORM(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    user_type: Mapped[str] = mapped_column(String(16), default="admin", nullable=False)
    # 小程序业务角色：normal=普通, risk_officer=风控专员（与 is_admin / 会员等级独立）
    role: Mapped[str] = mapped_column(String(32), default="normal", nullable=False)
    openid: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True)
    unionid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    wx_session_key: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    nickname: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    membership_level_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("membership_levels.id"), nullable=True
    )
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    preferences: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    favorite_stocks: Mapped[Optional[list[Any]]] = mapped_column(JSON, nullable=True)
    daily_quota: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    concurrent_limit: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    total_analyses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful_analyses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_analyses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    membership_level: Mapped[Optional["MembershipLevelORM"]] = relationship("MembershipLevelORM")


class BillingRecordORM(Base):
    __tablename__ = "billing_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    balance_before: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    is_free: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    stock_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    task_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    report_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    order_no: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    membership_level_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    membership_level_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    remark: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class PaymentOrderORM(Base):
    __tablename__ = "payment_orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    openid: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    wx_prepay_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    wx_transaction_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    description: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UserQuotaUsageORM(Base):
    __tablename__ = "user_quota_usage"
    __table_args__ = (UniqueConstraint("user_id", "period", name="uniq_user_period"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    free_generations_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    free_asks_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    membership_fee_charged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MpChatSessionORM(Base):
    """小程序问股会话"""

    __tablename__ = "mp_chat_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    stock_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    strategy_id: Mapped[str] = mapped_column(String(64), default="bull_trend", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False, index=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MpChatMessageORM(Base):
    """小程序问股消息"""

    __tablename__ = "mp_chat_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    stock_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="completed", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class MpNotificationORM(Base):
    """小程序站内通知（运营广播）"""

    __tablename__ = "mp_notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    notice_type: Mapped[str] = mapped_column(String(32), default="announcement", nullable=False)
    target_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    target_membership_level_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    target_user_ids: Mapped[Optional[list[Any]]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="published", nullable=False, index=True)
    recipient_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MpNotificationReadORM(Base):
    """用户已读记录"""

    __tablename__ = "mp_notification_reads"
    __table_args__ = (UniqueConstraint("notification_id", "user_id", name="uniq_notification_user_read"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    notification_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("mp_notifications.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BenefitCampaignORM(Base):
    """客户权益 / 活动定义"""

    __tablename__ = "benefit_campaigns"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    # draft / active / paused / ended
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False, index=True)
    # manual=仅指定用户; membership=会员等级; all=全体小程序用户
    grant_scope: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    # default=默认授予(自动发且不可再手动发); addon=增加授予(仅运营手动发)
    grant_mode: Mapped[str] = mapped_column(String(16), default="addon", nullable=False)
    membership_level_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("membership_levels.id"), nullable=True
    )
    # once / daily / monthly
    cycle_type: Mapped[str] = mapped_column(String(16), default="once", nullable=False)
    start_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    end_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    report_quota: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ask_quota: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    push_quota: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stackable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UserBenefitGrantORM(Base):
    """用户活动权益实例（可叠加；周期活动按 cycle_key 分桶）"""

    __tablename__ = "user_benefit_grants"
    __table_args__ = (
        UniqueConstraint("user_id", "campaign_id", "cycle_key", name="uniq_user_campaign_cycle"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    campaign_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("benefit_campaigns.id"), nullable=False, index=True
    )
    # membership_auto / all_auto / manual
    source: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    cycle_key: Mapped[str] = mapped_column(String(32), nullable=False)
    report_limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ask_limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    push_limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    report_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ask_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    push_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # active / exhausted / expired / revoked
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False, index=True)
    remark: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
