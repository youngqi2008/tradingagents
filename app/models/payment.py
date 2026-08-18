"""支付订单数据模型"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Annotated, Any

from bson import ObjectId
from pydantic import BaseModel, Field, ConfigDict, BeforeValidator, PlainSerializer, field_serializer

from app.utils.timezone import now_tz


def _validate_object_id(v: Any) -> ObjectId:
    if isinstance(v, ObjectId):
        return v
    if isinstance(v, str) and ObjectId.is_valid(v):
        return ObjectId(v)
    raise ValueError("Invalid ObjectId")


def _serialize_object_id(v: ObjectId) -> str:
    return str(v)


PyObjectId = Annotated[
    ObjectId,
    BeforeValidator(_validate_object_id),
    PlainSerializer(_serialize_object_id, return_type=str),
]


class PaymentStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    CLOSED = "closed"
    REFUNDED = "refunded"


class PaymentOrder(BaseModel):
    """充值订单"""

    id: Optional[int] = Field(default=None, alias="_id")
    order_no: str = Field(..., description="商户订单号")
    user_id: int
    openid: str = Field(..., description="微信 openid")
    amount: Decimal = Field(..., description="充值金额（元）")
    status: PaymentStatus = PaymentStatus.PENDING
    wx_prepay_id: Optional[str] = None
    wx_transaction_id: Optional[str] = None
    description: str = Field(default="账户充值")
    created_at: datetime = Field(default_factory=now_tz)
    paid_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=now_tz)

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)


class RechargeRequest(BaseModel):
    amount: Decimal = Field(..., ge=1, le=5000, description="充值金额（元），1～5000")


class PaymentOrderResponse(BaseModel):
    id: str
    order_no: str
    user_id: str
    amount: float
    status: str
    description: str
    created_at: datetime
    paid_at: Optional[datetime] = None

    @field_serializer("created_at", "paid_at")
    def serialize_datetime(self, dt: Optional[datetime], _info) -> Optional[str]:
        return dt.isoformat() if dt else None
