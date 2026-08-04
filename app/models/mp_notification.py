"""小程序站内通知模型"""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_serializer

from app.utils.timezone import now_tz

TargetType = Literal["all", "membership", "users"]
NoticeStatus = Literal["published", "revoked"]


class MpNotificationCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=128)
    content: str = Field(..., min_length=1)
    notice_type: str = Field(default="announcement")
    target_type: TargetType
    target_membership_level_id: Optional[str] = None
    target_user_ids: Optional[List[str]] = None


class MpNotificationResponse(BaseModel):
    id: str
    title: str
    content: str
    notice_type: str
    target_type: str
    target_membership_level_id: Optional[str] = None
    target_user_ids: Optional[List[str]] = None
    status: str
    recipient_count: int
    read_count: int = 0
    created_by: str
    created_at: datetime
    is_read: Optional[bool] = None
    read_at: Optional[datetime] = None

    @field_serializer("created_at", "read_at")
    def serialize_datetime(self, dt: Optional[datetime], _info) -> Optional[str]:
        return dt.isoformat() if dt else None


class MpNotificationListResponse(BaseModel):
    notifications: List[MpNotificationResponse]
    total: int
    unread_count: int = 0
