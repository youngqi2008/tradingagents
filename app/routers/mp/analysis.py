"""小程序分析 API - 生成时扣费"""

import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks

from app.routers.mp.deps import get_current_mp_user
from app.models.analysis import SingleAnalysisRequest, AnalysisParameters
from app.core.unified_config import unified_config
from app.services.simple_analysis_service import get_simple_analysis_service
from app.services.billing_service import billing_service, InsufficientBalanceError

router = APIRouter()
logger = logging.getLogger("webapi")


def _apply_system_analysis_models(request: SingleAnalysisRequest) -> SingleAnalysisRequest:
    """小程序研报使用后台「分析偏好」中的快速/深度模型（与 Web 单股分析一致）"""
    params = request.parameters or AnalysisParameters()
    quick = unified_config.get_quick_analysis_model()
    deep = unified_config.get_deep_analysis_model()
    params.quick_analysis_model = quick
    params.deep_analysis_model = deep
    request.parameters = params
    logger.info(f"📱 [MP] 使用系统分析偏好模型: quick={quick}, deep={deep}")
    return request


@router.post("/analysis/submit")
async def mp_submit_analysis(
    request: SingleAnalysisRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_mp_user),
):
    """提交单股分析（生成前扣费）"""
    symbol = request.get_symbol()
    if not symbol:
        raise HTTPException(status_code=400, detail="请提供股票代码")

    request = _apply_system_analysis_models(request)

    check = await billing_service.check_can_generate(user["id"])
    if not check.get("can_generate"):
        raise HTTPException(
            status_code=402,
            detail={
                "message": check.get("reason", "无法生成研报"),
                "required": check.get("price", 0),
                "balance": check.get("balance", 0),
            },
        )

    analysis_service = get_simple_analysis_service()
    result = await analysis_service.create_analysis_task(user["id"], request)
    task_id = result["task_id"]

    try:
        charge = await billing_service.charge_for_generation(
            user_id=user["id"],
            stock_code=symbol,
            task_id=task_id,
        )
        from app.core.database import get_mongo_db

        db = get_mongo_db()
        await db.analysis_tasks.update_one(
            {"task_id": task_id},
            {"$set": {"source": "miniprogram"}},
        )
    except InsufficientBalanceError as e:
        await analysis_service.memory_manager.delete_task(task_id)
        from app.core.database import get_mongo_db
        db = get_mongo_db()
        await db.analysis_tasks.update_one(
            {"task_id": task_id},
            {"$set": {"status": "cancelled", "message": "余额不足，任务已取消"}},
        )
        raise HTTPException(
            status_code=402,
            detail={
                "message": str(e),
                "required": float(e.required),
                "balance": float(e.balance),
            },
        )

    user_id = user["id"]

    async def run_analysis_task():
        try:
            service = get_simple_analysis_service()
            await service.execute_analysis_background(task_id, user_id, request)
        except Exception as e:
            logger.error(f"❌ [MP] 分析任务失败: {task_id}, {e}", exc_info=True)

    background_tasks.add_task(run_analysis_task)

    return {
        "success": True,
        "data": {
            **result,
            "charge": {
                "is_free": charge.is_free,
                "amount": float(charge.amount),
                "balance_after": float(charge.balance_after),
                "message": charge.message,
            },
        },
        "message": "分析任务已启动",
    }


@router.get("/analysis/task/{task_id}/status")
async def mp_get_task_status(
    task_id: str,
    user: dict = Depends(get_current_mp_user),
) -> Dict[str, Any]:
    from app.core.database import get_mongo_db

    db = get_mongo_db()
    owned = await db.analysis_tasks.find_one({"task_id": task_id, "user_id": user["id"]})
    if not owned:
        raise HTTPException(status_code=403, detail="无权访问该任务")

    analysis_service = get_simple_analysis_service()
    result = await analysis_service.get_task_status(task_id)
    if not result:
        result = {
            "task_id": task_id,
            "status": owned.get("status", "pending"),
            "progress": owned.get("progress", 0),
            "message": owned.get("message", ""),
        }
    return {"success": True, "data": result}
