"""计费流水数据模型"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_serializer

from app.utils.timezone import now_tz


class BillingActionType(str, Enum):
    GENERATE = "generate"
    ASK = "ask"
    DOWNLOAD = "download"
    RECHARGE = "recharge"
    REFUND = "refund"
    ADJUST = "adjust"
    MEMBERSHIP_FEE = "membership_fee"


class BillingRecord(BaseModel):
    """消费/充值流水"""

    id: Optional[int] = Field(default=None, alias="_id")
    user_id: int
    action_type: BillingActionType
    amount: Decimal = Field(default=Decimal("0"), description="金额（元），充值为正，消费为负")
    balance_before: Decimal = Field(default=Decimal("0"))
    balance_after: Decimal = Field(default=Decimal("0"))
    is_free: bool = Field(default=False, description="是否使用免费额度")
    stock_code: Optional[str] = None
    task_id: Optional[str] = None
    report_id: Optional[str] = None
    order_no: Optional[str] = None
    membership_level_id: Optional[str] = None
    membership_level_name: Optional[str] = None
    remark: str = Field(default="")
    created_at: datetime = Field(default_factory=now_tz)

    model_config = {"populate_by_name": True}


class BillingRecordResponse(BaseModel):
    id: str
    user_id: str
    action_type: str
    amount: float
    balance_before: float
    balance_after: float
    is_free: bool
    stock_code: Optional[str] = None
    task_id: Optional[str] = None
    report_id: Optional[str] = None
    order_no: Optional[str] = None
    membership_level_name: Optional[str] = None
    remark: str
    created_at: datetime

    @field_serializer("created_at")
    def serialize_datetime(self, dt: datetime, _info) -> str:
        return dt.isoformat()


class ChargeResult(BaseModel):
    """扣费结果"""

    success: bool
    is_free: bool = False
    amount: Decimal = Decimal("0")
    balance_after: Decimal = Decimal("0")
    billing_record_id: Optional[str] = None
    message: str = ""
