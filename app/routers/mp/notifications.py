"""小程序站内通知 API"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.routers.mp.deps import get_current_mp_user
from app.services.mp_notification_service import mp_notification_service

router = APIRouter()


@router.get("/notifications/unread-count")
async def mp_notification_unread_count(user: dict = Depends(get_current_mp_user)):
    count = await mp_notification_service.get_unread_count(user["id"])
    return {"success": True, "data": {"unread_count": count}}


@router.get("/notifications")
async def mp_list_notifications(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    notice_types: Optional[str] = Query(
        None,
        description="逗号分隔的 notice_type，如 buy_signal,sell_signal",
    ),
    user: dict = Depends(get_current_mp_user),
):
    types = None
    if notice_types:
        types = [t.strip() for t in notice_types.split(",") if t.strip()]
    items, total, unread = await mp_notification_service.list_for_user(
        user["id"], skip=skip, limit=limit, notice_types=types
    )
    return {
        "success": True,
        "data": {
            "notifications": [n.model_dump() for n in items],
            "total": total,
            "unread_count": unread,
        },
    }


@router.get("/notifications/{notification_id}")
async def mp_get_notification(
    notification_id: str,
    user: dict = Depends(get_current_mp_user),
):
    item = await mp_notification_service.get_for_user(user["id"], notification_id)
    if not item:
        raise HTTPException(status_code=404, detail="消息不存在")
    return {"success": True, "data": item.model_dump()}


@router.post("/notifications/{notification_id}/read")
async def mp_mark_notification_read(
    notification_id: str,
    user: dict = Depends(get_current_mp_user),
):
    ok = await mp_notification_service.mark_read(user["id"], notification_id)
    if not ok:
        raise HTTPException(status_code=404, detail="消息不存在或无权访问")
    unread = await mp_notification_service.get_unread_count(user["id"])
    return {"success": True, "data": {"unread_count": unread}, "message": "已标记已读"}


@router.post("/notifications/read-all")
async def mp_mark_all_notifications_read(user: dict = Depends(get_current_mp_user)):
    marked = await mp_notification_service.mark_all_read(user["id"])
    return {
        "success": True,
        "data": {"marked_count": marked, "unread_count": 0},
        "message": f"已标记 {marked} 条为已读",
    }
