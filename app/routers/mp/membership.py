"""小程序会员等级 API（升级/降级）"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.routers.mp.deps import get_current_mp_user
from app.services.billing_service import billing_service
from app.services.membership_service import membership_service
from app.services.user_service import user_service

router = APIRouter()


class ChangeMembershipRequest(BaseModel):
    membership_level_id: str = Field(..., description="目标会员等级 ID")


@router.get("/membership/levels")
async def list_mp_membership_levels(user: dict = Depends(get_current_mp_user)):
    """可选购的会员等级列表"""
    from app.services.benefit_service import get_level_benefit_templates

    levels = await membership_service.list_levels(active_only=True)
    benefit_templates = await get_level_benefit_templates()
    current_id = user.get("membership_level_id")
    if not current_id:
        default = await membership_service.get_default_level()
        current_id = str(default.id) if default else None

    level_items = []
    for level in levels:
        item = level.model_dump()
        tpl = benefit_templates.get(level.code) or {}
        item["benefit_monthly_report"] = tpl.get("monthly_report", 0)
        item["benefit_monthly_ask"] = tpl.get("monthly_ask", 0)
        item["benefit_monthly_push"] = tpl.get("monthly_push", 0)
        item["benefit_once_report"] = tpl.get("once_report", 0)
        item["benefit_once_ask"] = tpl.get("once_ask", 0)
        item["benefit_once_push"] = tpl.get("once_push", 0)
        if item["benefit_monthly_report"] >= 99999:
            item["benefit_monthly_report_text"] = "不限"
        else:
            item["benefit_monthly_report_text"] = str(item["benefit_monthly_report"])
        level_items.append(item)

    return {
        "success": True,
        "data": {
            "current_membership_level_id": current_id,
            "levels": level_items,
        },
    }


@router.post("/membership/change")
async def change_mp_membership(
    payload: ChangeMembershipRequest,
    user: dict = Depends(get_current_mp_user),
):
    """升级或降级会员等级"""
    target = await membership_service.get_level_by_id(payload.membership_level_id)
    if not target or not target.is_active:
        raise HTTPException(status_code=404, detail="会员等级不存在或已停用")

    current_id = user.get("membership_level_id")
    if current_id and str(target.id) == str(current_id):
        raise HTTPException(status_code=400, detail="您已是该会员等级")

    db_user = await user_service.get_user_by_id(user["id"])
    if not db_user:
        raise HTTPException(status_code=404, detail="用户不存在")

    current_level = None
    if current_id:
        current_level = await membership_service.get_level_by_id(current_id)
    if not current_level:
        current_level = await membership_service.get_default_level()

    monthly_fee = Decimal(str(target.monthly_price or 0))
    quota = await billing_service.get_quota_usage(user["id"])
    fee_paid = quota.get("membership_fee_charged", True)

    if monthly_fee > 0 and not fee_paid:
        balance = Decimal(str(db_user.balance or 0))
        if balance < monthly_fee:
            raise HTTPException(
                status_code=402,
                detail={
                    "message": f"变更至「{target.name}」需扣除本月会员费 ¥{monthly_fee}，余额不足",
                    "required": float(monthly_fee),
                    "balance": float(balance),
                },
            )

    prev_level_id = current_id
    ok = await user_service.update_mp_user_membership(user["id"], str(target.id))
    if not ok:
        raise HTTPException(status_code=500, detail="会员变更失败")

    fee_result = await billing_service.ensure_monthly_fee(user["id"])
    if monthly_fee > 0 and not fee_result.get("membership_fee_paid"):
        rollback_id = prev_level_id
        if not rollback_id:
            default = await membership_service.get_default_level()
            rollback_id = str(default.id) if default else None
        if rollback_id:
            await user_service.update_mp_user_membership(user["id"], rollback_id)
        raise HTTPException(
            status_code=402,
            detail={
                "message": fee_result.get("reason", "会员费扣除失败，变更已回滚"),
                "required": fee_result.get("amount", float(monthly_fee)),
                "balance": fee_result.get("balance", 0),
            },
        )

    current_sort = current_level.sort_order if current_level else -1
    is_upgrade = target.sort_order > current_sort
    action = "upgrade" if is_upgrade else "downgrade"
    verb = "升级" if is_upgrade else "降级"

    return {
        "success": True,
        "message": f"已{verb}为 {target.name}",
        "data": {
            "action": action,
            "membership_level_id": str(target.id),
            "membership_level_name": target.name,
            "balance": fee_result.get("balance", float(db_user.balance or 0)),
            "membership_fee_charged": fee_result.get("charged", False),
        },
    }
