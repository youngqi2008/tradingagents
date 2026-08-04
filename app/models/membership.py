"""会员等级数据模型"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict, field_serializer

from app.utils.timezone import now_tz


class MembershipLevel(BaseModel):
    """会员等级"""

    id: Optional[int] = Field(default=None, alias="_id")
    name: str = Field(..., description="等级名称")
    code: str = Field(..., description="等级代码，如 normal/vip/vvip")
    sort_order: int = Field(default=0, description="排序，越小越靠前")
    monthly_free_generations: int = Field(default=0, ge=0, description="每月免费研报次数")
    per_generation_price: Decimal = Field(default=Decimal("9.90"), description="研报超限单价（元）")
    monthly_free_asks: int = Field(default=0, ge=0, description="每月免费问股次数")
    per_ask_price: Decimal = Field(default=Decimal("9.90"), description="问股超限单价（元）")
    monthly_price: Decimal = Field(default=Decimal("0"), ge=0, description="月会员费（元），每月从余额扣除")
    description: str = Field(default="", description="等级说明")
    is_default: bool = Field(default=False, description="是否为默认等级（新用户）")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=now_tz)
    updated_at: datetime = Field(default_factory=now_tz)

    model_config = ConfigDict(populate_by_name=True)


class MembershipLevelCreate(BaseModel):
    name: str
    code: str
    sort_order: int = 0
    monthly_free_generations: int = 0
    per_generation_price: Decimal = Decimal("9.90")
    monthly_free_asks: int = 0
    per_ask_price: Decimal = Decimal("9.90")
    monthly_price: Decimal = Decimal("0")
    description: str = ""
    is_default: bool = False
    is_active: bool = True


class MembershipLevelUpdate(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None
    monthly_free_generations: Optional[int] = None
    per_generation_price: Optional[Decimal] = None
    monthly_free_asks: Optional[int] = None
    per_ask_price: Optional[Decimal] = None
    monthly_price: Optional[Decimal] = None
    description: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class MembershipLevelResponse(BaseModel):
    id: str
    name: str
    code: str
    sort_order: int
    monthly_free_generations: int
    per_generation_price: float
    monthly_free_asks: int
    per_ask_price: float
    monthly_price: float
    description: str
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, dt: datetime, _info) -> str:
        return dt.isoformat()
