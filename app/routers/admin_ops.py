"""运营后台 API - 用户/会员/计费管理"""

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.routers.mp.deps import get_current_admin_user
from app.services.user_service import user_service
from app.services.membership_service import membership_service
from app.services.billing_service import billing_service
from app.services.payment_service import payment_service
from app.services.mp_task_service import mp_task_service
from app.services.mp_chat_service import mp_chat_service
from app.services.mp_notification_service import mp_notification_service
from app.models.membership import MembershipLevelCreate, MembershipLevelUpdate
from app.models.mp_notification import MpNotificationCreate
from app.models.benefit import (
    AssignBenefitRequest,
    BenefitCampaignCreate,
    BenefitCampaignUpdate,
)
from app.models.role import (
    GrantRoleRequest,
    RoleCreate,
    RoleUpdate,
    UpdateUserRoleRequest,
)
from app.services.benefit_service import benefit_service
from app.services.role_service import role_service

router = APIRouter(prefix="/api/admin/ops", tags=["admin-ops"])


class AdjustBalanceRequest(BaseModel):
    amount: Decimal = Field(..., description="调整金额，正数增加，负数减少")
    remark: str = Field(default="管理员调账")


class UpdateMembershipRequest(BaseModel):
    membership_level_id: str


@router.get("/statistics")
async def get_ops_statistics(user: dict = Depends(get_current_admin_user)):
    stats = await billing_service.get_statistics()
    return {"success": True, "data": stats}


@router.get("/users")
async def list_mp_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    keyword: Optional[str] = None,
    role: Optional[str] = None,
    user: dict = Depends(get_current_admin_user),
):
    users = await user_service.list_mp_users(skip=skip, limit=limit, keyword=keyword, role=role)
    total = await user_service.count_mp_users(keyword=keyword, role=role)
    return {"success": True, "data": {"users": [u.model_dump() for u in users], "total": total}}


@router.get("/users/{user_id}")
async def get_mp_user_detail(
    user_id: str,
    admin: dict = Depends(get_current_admin_user),
):
    mp_user = await user_service.get_mp_user(user_id)
    if not mp_user:
        raise HTTPException(status_code=404, detail="用户不存在")

    quota = await billing_service.get_quota_usage(user_id)
    level = None
    if mp_user.membership_level_id:
        level = await membership_service.get_level_by_id(mp_user.membership_level_id)

    _, task_total = await mp_task_service.list_tasks(user_id=user_id, limit=1, skip=0)
    recharge_total = await billing_service.count_records(user_id=user_id, action_type="recharge")
    billing_total = await billing_service.count_records(user_id=user_id)
    order_total = await payment_service.count_orders(user_id=user_id)

    return {
        "success": True,
        "data": {
            "user": mp_user.model_dump(),
            "membership_level_name": level.name if level else "普通会员",
            "monthly_fee": quota.get("monthly_fee", 0),
            "membership_fee_paid": quota.get("membership_fee_charged", True),
            "report_free_used": quota.get("report_used", 0),
            "report_free_limit": quota.get("report_limit", 0),
            "report_free_remaining": quota.get("report_remaining", 0),
            "ask_free_used": quota.get("ask_used", 0),
            "ask_free_limit": quota.get("ask_limit", 0),
            "ask_free_remaining": quota.get("ask_remaining", 0),
            "report_benefit_remaining": quota.get("report_benefit_remaining", 0),
            "ask_benefit_remaining": quota.get("ask_benefit_remaining", 0),
            "push_benefit_remaining": quota.get("push_benefit_remaining", 0),
            "benefit_grants": quota.get("benefit_grants") or [],
            # 兼容旧字段
            "free_quota_used": quota.get("report_used", 0),
            "free_quota_limit": quota.get("report_limit", 0),
            "free_quota_remaining": quota.get("report_remaining", 0),
            "task_total": task_total,
            "recharge_count": recharge_total,
            "billing_count": billing_total,
            "order_count": order_total,
        },
    }


@router.put("/users/{user_id}/membership")
async def update_user_membership(
    user_id: str,
    payload: UpdateMembershipRequest,
    admin: dict = Depends(get_current_admin_user),
):
    level = await membership_service.get_level_by_id(payload.membership_level_id)
    if not level:
        raise HTTPException(status_code=404, detail="会员等级不存在")
    ok = await user_service.update_mp_user_membership(user_id, payload.membership_level_id)
    if not ok:
        raise HTTPException(status_code=404, detail="用户不存在或更新失败")
    return {"success": True, "message": f"已更新为 {level.name}"}


@router.get("/roles")
async def list_user_roles(
    active_only: bool = Query(False),
    admin: dict = Depends(get_current_admin_user),
):
    """角色管理列表（含用户数）"""
    roles = await role_service.list_roles(active_only=active_only)
    return {"success": True, "data": {"roles": [r.model_dump() for r in roles]}}


@router.post("/roles")
async def create_user_role(
    payload: RoleCreate,
    admin: dict = Depends(get_current_admin_user),
):
    try:
        role = await role_service.create_role(payload)
        return {"success": True, "data": role.model_dump(), "message": "角色已创建"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/roles/{role_id}")
async def update_user_role_def(
    role_id: str,
    payload: RoleUpdate,
    admin: dict = Depends(get_current_admin_user),
):
    try:
        role = await role_service.update_role(role_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    return {"success": True, "data": role.model_dump(), "message": "角色已更新"}


@router.delete("/roles/{role_id}")
async def deactivate_user_role_def(
    role_id: str,
    admin: dict = Depends(get_current_admin_user),
):
    try:
        ok = await role_service.deactivate_role(role_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="角色不存在")
    return {"success": True, "message": "角色已停用"}


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    payload: UpdateUserRoleRequest,
    admin: dict = Depends(get_current_admin_user),
):
    if not await role_service.is_valid_role(payload.role):
        raise HTTPException(status_code=400, detail="无效或已停用的角色")
    ok = await user_service.update_mp_user_role(user_id, payload.role)
    if not ok:
        raise HTTPException(status_code=404, detail="用户不存在或更新失败")
    return {
        "success": True,
        "message": f"已授予角色：{role_service.display_name(payload.role)}",
        "data": {"role": payload.role, "role_name": role_service.display_name(payload.role)},
    }


@router.post("/roles/grant")
async def grant_roles_batch(
    payload: GrantRoleRequest,
    admin: dict = Depends(get_current_admin_user),
):
    """批量授予角色"""
    if not await role_service.is_valid_role(payload.role):
        raise HTTPException(status_code=400, detail="无效或已停用的角色")
    result = await user_service.grant_mp_user_roles(payload.user_ids, payload.role)
    return {
        "success": True,
        "data": result,
        "message": (
            f"授予「{role_service.display_name(payload.role)}」完成："
            f"成功{result['success']} 跳过{result['skipped']} 失败{result['failed']}"
        ),
    }


@router.put("/users/{user_id}/active")
async def set_user_active(
    user_id: str,
    is_active: bool = Query(...),
    admin: dict = Depends(get_current_admin_user),
):
    ok = await user_service.set_mp_user_active(user_id, is_active)
    if not ok:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"success": True, "message": "已更新用户状态"}


@router.post("/users/{user_id}/adjust-balance")
async def adjust_user_balance(
    user_id: str,
    payload: AdjustBalanceRequest,
    admin: dict = Depends(get_current_admin_user),
):
    try:
        record = await billing_service.adjust_balance(
            user_id=user_id,
            amount=payload.amount,
            remark=payload.remark,
            operator=admin.get("username", "admin"),
        )
        return {
            "success": True,
            "data": {"balance_after": float(record.balance_after)},
            "message": "调账成功",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/membership-levels")
async def list_membership_levels(admin: dict = Depends(get_current_admin_user)):
    levels = await membership_service.list_levels()
    return {"success": True, "data": {"levels": [l.model_dump() for l in levels]}}


@router.post("/membership-levels")
async def create_membership_level(
    payload: MembershipLevelCreate,
    admin: dict = Depends(get_current_admin_user),
):
    level = await membership_service.create_level(payload)
    if not level:
        raise HTTPException(status_code=400, detail="等级代码已存在")
    return {"success": True, "data": level.model_dump(), "message": "创建成功"}


@router.put("/membership-levels/{level_id}")
async def update_membership_level(
    level_id: str,
    payload: MembershipLevelUpdate,
    admin: dict = Depends(get_current_admin_user),
):
    level = await membership_service.update_level(level_id, payload)
    if not level:
        raise HTTPException(status_code=404, detail="等级不存在")
    return {"success": True, "data": level.model_dump(), "message": "更新成功"}


@router.delete("/membership-levels/{level_id}")
async def delete_membership_level(
    level_id: str,
    admin: dict = Depends(get_current_admin_user),
):
    ok = await membership_service.delete_level(level_id)
    if not ok:
        raise HTTPException(status_code=400, detail="无法删除（默认等级或不存在）")
    return {"success": True, "message": "已停用"}


@router.get("/billing-records")
async def list_billing_records(
    user_id: Optional[str] = None,
    action_type: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    admin: dict = Depends(get_current_admin_user),
):
    records = await billing_service.list_records(
        user_id=user_id, skip=skip, limit=limit, action_type=action_type
    )
    total = await billing_service.count_records(user_id=user_id, action_type=action_type)
    return {"success": True, "data": {"records": [r.model_dump() for r in records], "total": total}}


@router.get("/payment-orders")
async def list_payment_orders(
    user_id: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    admin: dict = Depends(get_current_admin_user),
):
    orders = await payment_service.list_orders(user_id=user_id, skip=skip, limit=limit)
    total = await payment_service.count_orders(user_id=user_id)
    return {"success": True, "data": {"orders": [o.model_dump() for o in orders], "total": total}}


@router.get("/analysis-tasks")
async def list_mp_analysis_tasks(
    status: Optional[str] = None,
    user_id: Optional[str] = None,
    stock_code: Optional[str] = None,
    keyword: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    admin: dict = Depends(get_current_admin_user),
):
    tasks, total = await mp_task_service.list_tasks(
        status=status,
        user_id=user_id,
        stock_code=stock_code,
        keyword=keyword,
        skip=skip,
        limit=limit,
    )
    return {"success": True, "data": {"tasks": tasks, "total": total, "skip": skip, "limit": limit}}


@router.get("/analysis-tasks/{task_id}")
async def get_mp_analysis_task(
    task_id: str,
    admin: dict = Depends(get_current_admin_user),
):
    task = await mp_task_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"success": True, "data": task}


@router.post("/analysis-tasks/{task_id}/mark-failed")
async def admin_mark_mp_task_failed(
    task_id: str,
    admin: dict = Depends(get_current_admin_user),
):
    try:
        await mp_task_service.mark_failed(task_id)
        return {"success": True, "message": "任务已标记为失败"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/analysis-tasks/{task_id}")
async def admin_delete_mp_task(
    task_id: str,
    admin: dict = Depends(get_current_admin_user),
):
    try:
        deleted = await mp_task_service.delete_task(task_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="任务不存在")
        return {"success": True, "message": "任务已删除"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class ChatSessionStatusUpdate(BaseModel):
    status: str = Field(..., description="active | disabled | deleted")


@router.get("/chat-sessions")
async def list_mp_chat_sessions(
    status: Optional[str] = None,
    user_id: Optional[str] = None,
    keyword: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    admin: dict = Depends(get_current_admin_user),
):
    sessions, total = await mp_chat_service.list_sessions_admin(
        status=status,
        user_id=user_id,
        keyword=keyword,
        skip=skip,
        limit=limit,
    )
    return {"success": True, "data": {"sessions": sessions, "total": total, "skip": skip, "limit": limit}}


@router.get("/chat-sessions/{session_id}")
async def get_mp_chat_session(
    session_id: str,
    admin: dict = Depends(get_current_admin_user),
):
    session = await mp_chat_service.get_session_admin(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="问股会话不存在")
    return {"success": True, "data": session}


@router.put("/chat-sessions/{session_id}/status")
async def update_mp_chat_session_status(
    session_id: str,
    body: ChatSessionStatusUpdate,
    admin: dict = Depends(get_current_admin_user),
):
    ok = await mp_chat_service.set_session_status_admin(session_id, body.status)
    if not ok:
        raise HTTPException(status_code=400, detail="更新失败，会话不存在或状态无效")
    return {"success": True, "message": "状态已更新"}


@router.delete("/chat-sessions/{session_id}")
async def delete_mp_chat_session(
    session_id: str,
    admin: dict = Depends(get_current_admin_user),
):
    ok = await mp_chat_service.set_session_status_admin(session_id, "deleted")
    if not ok:
        raise HTTPException(status_code=404, detail="问股会话不存在")
    return {"success": True, "message": "会话已删除"}


@router.get("/notifications")
async def list_mp_notifications(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    admin: dict = Depends(get_current_admin_user),
):
    items, total = await mp_notification_service.list_admin(skip=skip, limit=limit)
    return {
        "success": True,
        "data": {
            "notifications": [n.model_dump() for n in items],
            "total": total,
        },
    }


@router.post("/notifications")
async def create_mp_notification(
    payload: MpNotificationCreate,
    admin: dict = Depends(get_current_admin_user),
):
    try:
        item = await mp_notification_service.create_notification(
            payload,
            created_by=admin.get("username", "admin"),
        )
        return {
            "success": True,
            "data": item.model_dump(),
            "message": f"已发送给 {item.recipient_count} 位用户",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/notifications/{notification_id}/revoke")
async def revoke_mp_notification(
    notification_id: str,
    admin: dict = Depends(get_current_admin_user),
):
    ok = await mp_notification_service.revoke(notification_id)
    if not ok:
        raise HTTPException(status_code=404, detail="通知不存在")
    return {"success": True, "message": "已撤回"}


# ---------- 客户权益 / 活动 ----------

@router.get("/benefit-campaigns")
async def list_benefit_campaigns(
    status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    admin: dict = Depends(get_current_admin_user),
):
    items = await benefit_service.list_campaigns(status=status, skip=skip, limit=limit)
    return {"success": True, "data": {"campaigns": [c.model_dump() for c in items]}}


@router.post("/benefit-campaigns")
async def create_benefit_campaign(
    payload: BenefitCampaignCreate,
    admin: dict = Depends(get_current_admin_user),
):
    try:
        item = await benefit_service.create_campaign(payload)
        return {"success": True, "data": item.model_dump(), "message": "活动已创建"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/benefit-campaigns/{campaign_id}")
async def update_benefit_campaign(
    campaign_id: str,
    payload: BenefitCampaignUpdate,
    admin: dict = Depends(get_current_admin_user),
):
    try:
        item = await benefit_service.update_campaign(campaign_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not item:
        raise HTTPException(status_code=404, detail="活动不存在")
    return {"success": True, "data": item.model_dump(), "message": "已更新"}


@router.get("/users/{user_id}/benefits")
async def list_user_benefits(
    user_id: str,
    include_inactive: bool = Query(False),
    admin: dict = Depends(get_current_admin_user),
):
    grants = await benefit_service.list_user_grants(user_id, include_inactive=include_inactive)
    summary = await benefit_service.summarize_user_benefits(user_id)
    return {
        "success": True,
        "data": {
            "grants": [g.model_dump() for g in grants],
            "summary": summary,
        },
    }


@router.post("/users/{user_id}/benefits")
async def assign_user_benefit(
    user_id: str,
    payload: AssignBenefitRequest,
    admin: dict = Depends(get_current_admin_user),
):
    try:
        grant = await benefit_service.assign_to_user(user_id, payload)
        return {"success": True, "data": grant.model_dump(), "message": "已发放权益"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/benefit-grants/{grant_id}/revoke")
async def revoke_user_benefit(
    grant_id: str,
    admin: dict = Depends(get_current_admin_user),
):
    ok = await benefit_service.revoke_grant(grant_id)
    if not ok:
        raise HTTPException(status_code=404, detail="权益记录不存在")
    return {"success": True, "message": "已撤销"}


# ---------- 自选股订阅（运营） ----------


class OpsFavoriteAdd(BaseModel):
    stock_code: str = Field(..., min_length=1, max_length=16)
    stock_name: str = Field("", max_length=64)
    market: str = Field("A股", max_length=16)
    notes: str = ""


@router.get("/favorites")
async def admin_list_favorites(
    user_id: Optional[str] = None,
    stock_code: Optional[str] = None,
    mp_only: bool = True,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    admin: dict = Depends(get_current_admin_user),
):
    from app.services.favorites_service import favorites_service
    from app.services.user_service import user_service

    data = await favorites_service.list_favorites_admin(
        user_id=user_id,
        stock_code=stock_code,
        mp_only=mp_only,
        skip=skip,
        limit=limit,
    )
    # 补齐小程序用户昵称
    nick_cache: dict = {}
    for item in data["items"]:
        if not item.get("is_mp_user"):
            item["nickname"] = ""
            continue
        uid = item["user_id"]
        if uid not in nick_cache:
            u = await user_service.get_user_by_id(uid)
            nick_cache[uid] = (u.nickname if u else "") or ""
        item["nickname"] = nick_cache[uid]
    return {"success": True, "data": data}


@router.get("/users/{user_id}/favorites")
async def admin_user_favorites(
    user_id: str,
    admin: dict = Depends(get_current_admin_user),
):
    from app.services.favorites_service import favorites_service

    key = favorites_service.mp_user_key(user_id)
    items = await favorites_service.get_user_favorites(key)
    return {"success": True, "data": {"favorites": items, "total": len(items)}}


@router.post("/users/{user_id}/favorites")
async def admin_add_user_favorite(
    user_id: str,
    payload: OpsFavoriteAdd,
    admin: dict = Depends(get_current_admin_user),
):
    from app.services.favorites_service import favorites_service

    code = payload.stock_code.strip().upper()
    if code.isdigit():
        code = code.zfill(6)
    key = favorites_service.mp_user_key(user_id)
    if await favorites_service.is_favorite(key, code):
        raise HTTPException(status_code=400, detail="该股票已在用户自选中")
    await favorites_service.add_favorite(
        key,
        stock_code=code,
        stock_name=(payload.stock_name or "").strip() or code,
        market=payload.market or "A股",
        notes=payload.notes or "",
    )
    items = await favorites_service.get_user_favorites(key)
    return {"success": True, "message": "已添加", "data": {"favorites": items}}


@router.delete("/users/{user_id}/favorites/{stock_code}")
async def admin_remove_user_favorite(
    user_id: str,
    stock_code: str,
    admin: dict = Depends(get_current_admin_user),
):
    from app.services.favorites_service import favorites_service

    code = stock_code.strip().upper()
    if code.isdigit():
        code = code.zfill(6)
    ok = await favorites_service.remove_favorite(favorites_service.mp_user_key(user_id), code)
    if not ok:
        raise HTTPException(status_code=404, detail="自选中不存在该股票")
    return {"success": True, "message": "已移除"}


@router.post("/favorites/digest/run")
async def admin_run_favorites_digest(
    user_id: Optional[str] = None,
    admin: dict = Depends(get_current_admin_user),
):
    """手动触发自选股日报 → 小程序站内信（替代企业微信 STOCK_LIST 推送）"""
    from app.services.favorites_digest_service import favorites_digest_service

    result = await favorites_digest_service.run_daily_digest(
        user_id=user_id,
        created_by=f"admin:{admin.get('id') or admin.get('username') or 'ops'}",
    )
    return {"success": True, "data": result, "message": f"已推送 {result.get('sent', 0)} 人"}


@router.post("/market-review/run")
async def admin_run_market_review(
    admin: dict = Depends(get_current_admin_user),
):
    """手动触发大盘复盘 → 全体小程序站内信（移植 DSA 企微下午推送）"""
    from app.services.market_review_service import market_review_service

    result = await market_review_service.run_and_push(
        created_by=f"admin:{admin.get('id') or admin.get('username') or 'ops'}",
    )
    return {
        "success": True,
        "data": result,
        "message": f"大盘复盘已推送（通知 {result.get('notification_id') or '-'}）",
    }
