"""小程序风控消息 API（仅启用中的风控专员）"""

import time
from collections import defaultdict
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, model_validator

from app.models.mp_notification import MpNotificationCreate
from app.models.operation_log import ActionType
from app.routers.mp.deps import get_current_risk_officer
from app.services.membership_service import membership_service
from app.services.mp_notification_service import mp_notification_service
from app.services.operation_log_service import log_operation

router = APIRouter()

# 风控群发限流：每用户每小时最多 N 次
_RISK_SEND_LIMIT_PER_HOUR = 5
_RISK_CONTENT_MAX_LEN = 2000
_rate_buckets: dict[str, list[float]] = defaultdict(list)


class RiskMessageCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=128)
    content: str = Field(..., min_length=1, max_length=_RISK_CONTENT_MAX_LEN)
    target_type: Literal["all", "membership"] = Field(
        ..., description="all=全体小程序用户, membership=指定会员等级（可多选）"
    )
    target_membership_level_id: Optional[str] = Field(
        None, description="兼容单选；多选请用 target_membership_level_ids"
    )
    target_membership_level_ids: Optional[List[str]] = Field(
        None, description="会员等级 ID 列表（多选）"
    )

    @model_validator(mode="after")
    def normalize_membership_ids(self):
        if self.target_type != "membership":
            return self
        ids: list[str] = []
        if self.target_membership_level_ids:
            ids.extend(str(x).strip() for x in self.target_membership_level_ids if str(x).strip())
        if self.target_membership_level_id and str(self.target_membership_level_id).strip():
            ids.append(str(self.target_membership_level_id).strip())
        seen = set()
        unique: list[str] = []
        for i in ids:
            if i not in seen:
                seen.add(i)
                unique.append(i)
        self.target_membership_level_ids = unique
        if unique:
            self.target_membership_level_id = unique[0]
        return self


def _enforce_rate_limit(user_id: str) -> None:
    now = time.time()
    window = [t for t in _rate_buckets.get(user_id, []) if now - t < 3600]
    if len(window) >= _RISK_SEND_LIMIT_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail=f"发送过于频繁，每小时最多 {_RISK_SEND_LIMIT_PER_HOUR} 条",
        )
    window.append(now)
    _rate_buckets[user_id] = window


@router.post("/risk-messages")
async def create_risk_message(
    payload: RiskMessageCreate,
    request: Request,
    user: dict = Depends(get_current_risk_officer),
):
    """风控专员发送站内消息：全体或按会员等级（支持多选，限流 + 审计）"""
    user_id = str(user["id"])
    _enforce_rate_limit(user_id)

    level_ids: list[str] = []
    if payload.target_type == "membership":
        level_ids = list(payload.target_membership_level_ids or [])
        if not level_ids:
            raise HTTPException(status_code=400, detail="请至少选择一个会员等级")
        for lid in level_ids:
            level = await membership_service.get_level_by_id(lid)
            if not level or not level.is_active:
                raise HTTPException(status_code=400, detail=f"会员等级不存在或已停用: {lid}")

    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")
    title = payload.title.strip()
    content = payload.content.strip()

    created_items = []
    try:
        if payload.target_type == "all":
            item = await mp_notification_service.create_notification(
                MpNotificationCreate(
                    title=title,
                    content=content,
                    notice_type="risk_alert",
                    target_type="all",
                ),
                created_by=f"risk:{user_id}",
            )
            created_items.append(item)
        else:
            # 每个等级各发一条，保证可见性过滤仍按单等级字段匹配
            for lid in level_ids:
                item = await mp_notification_service.create_notification(
                    MpNotificationCreate(
                        title=title,
                        content=content,
                        notice_type="risk_alert",
                        target_type="membership",
                        target_membership_level_id=lid,
                    ),
                    created_by=f"risk:{user_id}",
                )
                created_items.append(item)
    except ValueError as e:
        await log_operation(
            user_id=user_id,
            username=user.get("nickname") or user.get("username") or user_id,
            action_type=ActionType.RISK_MESSAGE,
            action="发送风控消息失败",
            details={"error": str(e), "target_type": payload.target_type},
            success=False,
            error_message=str(e),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        raise HTTPException(status_code=400, detail=str(e))

    total_recipients = sum(i.recipient_count for i in created_items)
    primary = created_items[0]
    await log_operation(
        user_id=user_id,
        username=user.get("nickname") or user.get("username") or user_id,
        action_type=ActionType.RISK_MESSAGE,
        action="发送风控消息",
        details={
            "notification_ids": [i.id for i in created_items],
            "notification_id": primary.id,
            "target_type": payload.target_type,
            "target_membership_level_ids": level_ids or None,
            "target_membership_level_id": level_ids[0] if level_ids else None,
            "recipient_count": total_recipients,
            "level_count": len(created_items),
            "title": title,
        },
        success=True,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    level_hint = f"，覆盖 {len(level_ids)} 个会员等级" if len(level_ids) > 1 else ""
    return {
        "success": True,
        "data": {
            **primary.model_dump(),
            "recipient_count": total_recipients,
            "notification_ids": [i.id for i in created_items],
            "target_membership_level_ids": level_ids or None,
        },
        "message": f"已发送，预计触达 {total_recipients} 人{level_hint}",
    }


@router.get("/risk-messages")
async def list_my_risk_messages(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_risk_officer),
):
    """风控专员查看自己发出的风控消息"""
    items, total = await mp_notification_service.list_admin(
        skip=skip,
        limit=limit,
        notice_type="risk_alert",
        created_by=f"risk:{user['id']}",
    )
    return {
        "success": True,
        "data": {
            "notifications": [n.model_dump() for n in items],
            "total": total,
        },
    }
