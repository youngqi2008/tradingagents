"""客户权益 / 活动 Pydantic 模型"""

from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel, Field


CycleType = Literal["once", "daily", "monthly"]
GrantScope = Literal["manual", "membership", "all"]
# default=系统自动默认授予(不可再手动发); addon=增加授予(仅运营手动)
GrantMode = Literal["default", "addon"]
CampaignStatus = Literal["draft", "active", "paused", "ended"]
BenefitKind = Literal["report", "ask", "push"]


class BenefitCampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    code: str = Field(..., min_length=1, max_length=64)
    description: str = ""
    status: CampaignStatus = "draft"
    grant_scope: GrantScope = "manual"
    grant_mode: GrantMode = "addon"
    membership_level_id: Optional[str] = None
    cycle_type: CycleType = "once"
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    report_quota: int = Field(0, ge=0)
    ask_quota: int = Field(0, ge=0)
    push_quota: int = Field(0, ge=0)
    stackable: bool = True
    priority: int = 100


class BenefitCampaignUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[CampaignStatus] = None
    grant_scope: Optional[GrantScope] = None
    grant_mode: Optional[GrantMode] = None
    membership_level_id: Optional[str] = None
    cycle_type: Optional[CycleType] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    report_quota: Optional[int] = Field(None, ge=0)
    ask_quota: Optional[int] = Field(None, ge=0)
    push_quota: Optional[int] = Field(None, ge=0)
    stackable: Optional[bool] = None
    priority: Optional[int] = None


class BenefitCampaignResponse(BaseModel):
    id: str
    name: str
    code: str
    description: str
    status: str
    grant_scope: str
    grant_mode: str = "addon"
    membership_level_id: Optional[str] = None
    cycle_type: str
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    report_quota: int
    ask_quota: int
    push_quota: int
    stackable: bool
    priority: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AssignBenefitRequest(BaseModel):
    campaign_id: str
    remark: str = ""
    # 可选覆盖额度；为空则用活动定义
    report_quota: Optional[int] = Field(None, ge=0)
    ask_quota: Optional[int] = Field(None, ge=0)
    push_quota: Optional[int] = Field(None, ge=0)
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None


class UserBenefitGrantResponse(BaseModel):
    id: str
    user_id: str
    campaign_id: str
    campaign_name: str = ""
    campaign_code: str = ""
    source: str
    cycle_key: str
    report_limit: int
    ask_limit: int
    push_limit: int
    report_used: int
    ask_used: int
    push_used: int
    report_remaining: int = 0
    ask_remaining: int = 0
    push_remaining: int = 0
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    status: str
    remark: str = ""
    created_at: Optional[datetime] = None
