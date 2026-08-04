"""小程序用户 API"""

from decimal import Decimal

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field

from app.routers.mp.deps import get_current_mp_user
from app.services.user_service import user_service
from app.services.billing_service import billing_service
from app.services.membership_service import membership_service
from app.services.payment_service import payment_service, RECHARGE_AMOUNTS
from app.models.payment import RechargeRequest
from app.models.role import DEFAULT_MP_ROLE, role_display_name

router = APIRouter()


@router.get("/user/profile")
async def get_profile(user: dict = Depends(get_current_mp_user)):
    import logging

    logger = logging.getLogger("webapi")
    db_user = await user_service.get_user_by_id(user["id"])
    if not db_user:
        raise HTTPException(status_code=404, detail="用户不存在")

    level = None
    try:
        if db_user.membership_level_id:
            level = await membership_service.get_level_by_id(str(db_user.membership_level_id))
        if not level:
            level = await membership_service.get_default_level()
    except Exception as e:
        logger.exception("获取会员等级失败: %s", e)

    quota: dict = {}
    check: dict = {}
    ask_check: dict = {}
    try:
        check = await billing_service.check_can_generate(user["id"])
        ask_check = await billing_service.check_can_ask(user["id"])
        quota = await billing_service.get_quota_usage(user["id"])
    except Exception as e:
        logger.exception("获取额度/权益失败（资料页降级返回）: %s", e)

    return {
        "success": True,
        "data": {
            "id": user["id"],
            "nickname": db_user.nickname,
            "avatar_url": db_user.avatar_url,
            "balance": float(db_user.balance or 0),
            "role": getattr(db_user, "role", None) or DEFAULT_MP_ROLE,
            "role_name": role_display_name(getattr(db_user, "role", None)),
            "membership_level_id": db_user.membership_level_id,
            "membership_level_name": (level.name if level else None)
            or check.get("membership_level_name")
            or "普通会员",
            "monthly_fee": quota.get("monthly_fee", 0),
            "membership_fee_paid": quota.get("membership_fee_charged", True),
            "monthly_free_generations": getattr(level, "monthly_free_generations", 0) or 0,
            "monthly_free_asks": getattr(level, "monthly_free_asks", 0) or 0,
            "report_free_used": quota.get("report_used", 0),
            "report_free_remaining": quota.get("report_remaining", 0),
            "ask_free_used": quota.get("ask_used", 0),
            "ask_free_remaining": quota.get("ask_remaining", 0),
            "per_generation_price": float(getattr(level, "per_generation_price", 9.9) or 9.9),
            "per_ask_price": float(getattr(level, "per_ask_price", 9.9) or 9.9),
            "can_generate": check.get("can_generate", False),
            "can_ask": ask_check.get("can_use", False),
            "report_benefit_remaining": quota.get("report_benefit_remaining", 0),
            "ask_benefit_remaining": quota.get("ask_benefit_remaining", 0),
            "push_benefit_remaining": quota.get("push_benefit_remaining", 0),
            "benefit_grants": quota.get("benefit_grants") or [],
            "free_used": quota.get("report_used", 0),
            "free_remaining": quota.get("report_remaining", 0),
        },
    }


@router.get("/user/benefits")
async def get_user_benefits(user: dict = Depends(get_current_mp_user)):
    """小程序：我的活动权益剩余次数"""
    from app.services.benefit_service import benefit_service
    data = await benefit_service.summarize_user_benefits(user["id"])
    return {"success": True, "data": data}


@router.get("/user/billing-records")
async def get_billing_records(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_mp_user),
):
    records = await billing_service.list_records(user_id=user["id"], skip=skip, limit=limit)
    return {"success": True, "data": {"records": [r.model_dump() for r in records]}}


@router.get("/payment/recharge-options")
async def get_recharge_options():
    return {
        "success": True,
        "data": {"amounts": [float(a) for a in RECHARGE_AMOUNTS]},
    }


@router.post("/payment/recharge")
async def create_recharge(
    payload: RechargeRequest,
    user: dict = Depends(get_current_mp_user),
):
    db_user = await user_service.get_user_by_id(user["id"])
    if not db_user or not db_user.openid:
        raise HTTPException(status_code=400, detail="用户信息异常")
    try:
        result = await payment_service.create_recharge_order(
            user_id=user["id"],
            openid=db_user.openid,
            amount=payload.amount,
        )
        return {"success": True, "data": result, "message": result.get("message", "订单创建成功")}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/payment/orders")
async def list_payment_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_mp_user),
):
    orders = await payment_service.list_orders(user_id=user["id"], skip=skip, limit=limit)
    return {"success": True, "data": {"orders": [o.model_dump() for o in orders]}}


@router.get("/billing/check")
async def check_billing(user: dict = Depends(get_current_mp_user)):
    check = await billing_service.check_can_generate(user["id"])
    return {"success": True, "data": check}
