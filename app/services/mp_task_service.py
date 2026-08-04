"""小程序研报任务管理服务（运营后台）"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.core.database import get_mongo_db
from app.routers.reports import get_stock_name
from app.services.simple_analysis_service import get_simple_analysis_service
from app.services.user_service import user_service
from app.utils.timezone import to_config_tz

try:
    from tradingagents.utils.logging_manager import get_logger
except ImportError:
    import logging

    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)

logger = get_logger("mp_task_service")

MP_TASK_SOURCE = "miniprogram"


def _status_filter(status: Optional[str]) -> Optional[Dict[str, Any]]:
    if not status:
        return None
    if status == "processing":
        return {"$in": ["processing", "running", "pending"]}
    return status


def _format_dt(value: Any) -> str:
    if not value:
        return ""
    if hasattr(value, "isoformat"):
        dt = to_config_tz(value) if isinstance(value, datetime) else value
        return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)
    return str(value)


def _serialize_task(doc: dict, user_map: Dict[str, Dict[str, str]]) -> dict:
    user_id = str(doc.get("user_id") or doc.get("user") or "")
    user_info = user_map.get(user_id, {})
    code = doc.get("stock_code") or doc.get("stock_symbol") or doc.get("symbol") or ""
    created_at = doc.get("created_at") or doc.get("started_at")
    return {
        "task_id": doc.get("task_id", ""),
        "user_id": user_id,
        "user_nickname": user_info.get("nickname", ""),
        "user_openid": user_info.get("openid", ""),
        "stock_code": code,
        "stock_name": doc.get("stock_name") or get_stock_name(code),
        "status": doc.get("status", "pending"),
        "progress": int(doc.get("progress", 0) or 0),
        "message": doc.get("message", ""),
        "source": doc.get("source", ""),
        "created_at": _format_dt(created_at),
        "completed_at": _format_dt(doc.get("completed_at")),
        "summary": (doc.get("result") or {}).get("summary", ""),
    }


class MpTaskService:
    async def _get_mp_user_map(self) -> Dict[str, Dict[str, str]]:
        return await user_service.get_mp_user_id_map()

    async def _build_query(
        self,
        *,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        stock_code: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Dict[str, str]]]:
        user_map = await self._get_mp_user_map()
        mp_ids = list(user_map.keys())

        if user_id:
            if user_id not in user_map:
                return {"task_id": "__none__"}, user_map
            scope = {"user_id": user_id}
        else:
            scope = {
                "$or": [
                    {"source": MP_TASK_SOURCE},
                    {"user_id": {"$in": mp_ids}},
                ]
            }

        clauses: List[Dict[str, Any]] = [scope]
        status_q = _status_filter(status)
        if status_q is not None:
            clauses.append({"status": status_q})
        if stock_code:
            code = stock_code.strip()
            clauses.append(
                {
                    "$or": [
                        {"stock_code": code},
                        {"stock_symbol": code},
                        {"symbol": code},
                    ]
                }
            )
        if keyword:
            kw = keyword.strip()
            matched_ids = [
                uid
                for uid, info in user_map.items()
                if kw in (info.get("nickname") or "")
                or kw in (info.get("openid") or "")
            ]
            clauses.append(
                {
                    "$or": [
                        {"task_id": {"$regex": kw, "$options": "i"}},
                        {"stock_code": {"$regex": kw, "$options": "i"}},
                        {"stock_symbol": {"$regex": kw, "$options": "i"}},
                        {"stock_name": {"$regex": kw, "$options": "i"}},
                        {"user_id": {"$in": matched_ids}},
                    ]
                }
            )

        query: Dict[str, Any] = {"$and": clauses} if len(clauses) > 1 else clauses[0]
        return query, user_map

    async def list_tasks(
        self,
        *,
        status: Optional[str] = None,
        user_id: Optional[str] = None,
        stock_code: Optional[str] = None,
        keyword: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[dict], int]:
        query, user_map = await self._build_query(
            user_id=user_id,
            status=status,
            stock_code=stock_code,
            keyword=keyword,
        )
        db = get_mongo_db()
        total = await db.analysis_tasks.count_documents(query)
        cursor = (
            db.analysis_tasks.find(query)
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        tasks = []
        async for doc in cursor:
            tasks.append(_serialize_task(doc, user_map))
        return tasks, total

    async def get_task(self, task_id: str) -> Optional[dict]:
        db = get_mongo_db()
        doc = await db.analysis_tasks.find_one({"task_id": task_id})
        if not doc:
            return None
        user_map = await self._get_mp_user_map()
        if not await self._is_mp_task(doc, user_map):
            return None
        task = _serialize_task(doc, user_map)
        result = doc.get("result") or {}
        task.update(
            {
                "recommendation": result.get("recommendation", ""),
                "risk_level": result.get("risk_level", ""),
                "reports": result.get("reports", {}),
                "error_message": doc.get("last_error") or doc.get("message", ""),
            }
        )
        return task

    async def _is_mp_task(
        self, doc: dict, user_map: Optional[Dict[str, Dict[str, str]]] = None
    ) -> bool:
        if doc.get("source") == MP_TASK_SOURCE:
            return True
        user_id = str(doc.get("user_id") or doc.get("user") or "")
        if not user_id:
            return False
        if user_map is None:
            user_map = await self._get_mp_user_map()
        return user_id in user_map

    async def _require_mp_task(self, task_id: str) -> dict:
        db = get_mongo_db()
        doc = await db.analysis_tasks.find_one({"task_id": task_id})
        if not doc:
            raise ValueError("任务不存在")
        if not await self._is_mp_task(doc):
            raise ValueError("非小程序研报任务，无法操作")
        return doc

    async def mark_failed(self, task_id: str) -> bool:
        await self._require_mp_task(task_id)
        from app.services.memory_state_manager import TaskStatus

        svc = get_simple_analysis_service()
        await svc.memory_manager.update_task_status(
            task_id=task_id,
            status=TaskStatus.FAILED,
            message="管理员手动标记为失败",
            error_message="管理员手动标记为失败",
        )
        db = get_mongo_db()
        result = await db.analysis_tasks.update_one(
            {"task_id": task_id},
            {
                "$set": {
                    "status": "failed",
                    "last_error": "管理员手动标记为失败",
                    "message": "管理员手动标记为失败",
                    "completed_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        return result.modified_count > 0 or result.matched_count > 0

    async def delete_task(self, task_id: str) -> bool:
        await self._require_mp_task(task_id)
        svc = get_simple_analysis_service()
        await svc.memory_manager.remove_task(task_id)
        db = get_mongo_db()
        result = await db.analysis_tasks.delete_one({"task_id": task_id})
        return result.deleted_count > 0


mp_task_service = MpTaskService()
