"""小程序报告 API - 下载免费（生成时已扣费）"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.routers.mp.deps import get_current_mp_user
from app.core.database import get_mongo_db
from app.routers.reports import _build_report_query, get_stock_name
from app.utils.timezone import to_config_tz

router = APIRouter()
logger = logging.getLogger("webapi")


async def _verify_report_owner(report_id: str, user_id: str) -> dict:
    db = get_mongo_db()
    query = _build_report_query(report_id)
    doc = await db.analysis_reports.find_one(query)
    if doc:
        task_id = doc.get("task_id", "")
        if task_id:
            task = await db.analysis_tasks.find_one({"task_id": task_id, "user_id": user_id})
            if not task:
                raise HTTPException(status_code=403, detail="无权访问该报告")
        return doc

    task = await db.analysis_tasks.find_one(
        {"$or": [{"task_id": report_id}, {"result.analysis_id": report_id}], "user_id": user_id},
    )
    if not task:
        raise HTTPException(status_code=404, detail="报告不存在")
    return {"task_doc": task, "from_task": True}


@router.get("/reports/list")
async def mp_list_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    user: dict = Depends(get_current_mp_user),
):
    db = get_mongo_db()
    query = {"user_id": user["id"], "status": {"$in": ["completed", "processing", "pending", "failed"]}}
    total = await db.analysis_tasks.count_documents(query)
    skip = (page - 1) * page_size
    cursor = db.analysis_tasks.find(query).sort("created_at", -1).skip(skip).limit(page_size)
    reports = []
    async for doc in cursor:
        code = doc.get("stock_code") or doc.get("stock_symbol", "")
        name = doc.get("stock_name") or get_stock_name(code)
        created_at = doc.get("created_at")
        created_at_tz = to_config_tz(created_at) if created_at else None
        reports.append({
            "id": doc.get("task_id", ""),
            "task_id": doc.get("task_id", ""),
            "stock_code": code,
            "stock_name": name,
            "status": doc.get("status", "pending"),
            "progress": doc.get("progress", 0),
            "created_at": created_at_tz.isoformat() if created_at_tz else "",
            "summary": (doc.get("result") or {}).get("summary", ""),
        })
    return {"success": True, "data": {"reports": reports, "total": total, "page": page, "page_size": page_size}}


@router.get("/reports/{report_id}")
async def mp_get_report(report_id: str, user: dict = Depends(get_current_mp_user)):
    db = get_mongo_db()
    task = await db.analysis_tasks.find_one({"task_id": report_id, "user_id": user["id"]})
    if not task:
        raise HTTPException(status_code=404, detail="报告不存在")

    result = task.get("result") or {}
    code = task.get("stock_code") or task.get("stock_symbol", "")
    return {
        "success": True,
        "data": {
            "id": report_id,
            "task_id": report_id,
            "stock_code": code,
            "stock_name": task.get("stock_name") or get_stock_name(code),
            "status": task.get("status", "pending"),
            "progress": task.get("progress", 0),
            "summary": result.get("summary", ""),
            "recommendation": result.get("recommendation", ""),
            "risk_level": result.get("risk_level", ""),
            "reports": result.get("reports", {}),
        },
    }


@router.get("/reports/{report_id}/download")
async def mp_download_report(
    report_id: str,
    format: str = Query("markdown", description="markdown, pdf, docx"),
    user: dict = Depends(get_current_mp_user),
):
    """下载报告（生成时已扣费，下载不再计费）"""
    db = get_mongo_db()
    task = await db.analysis_tasks.find_one({"task_id": report_id, "user_id": user["id"]})
    if not task:
        raise HTTPException(status_code=404, detail="报告不存在")
    if task.get("status") != "completed":
        raise HTTPException(status_code=400, detail="报告尚未生成完成")

    query = _build_report_query(report_id)
    doc = await db.analysis_reports.find_one(query)
    if not doc and task.get("result"):
        doc = {
            "stock_symbol": task.get("stock_code", ""),
            "analysis_date": (task.get("result") or {}).get("analysis_date", datetime.now().strftime("%Y-%m-%d")),
            "reports": (task.get("result") or {}).get("reports", {}),
            "summary": (task.get("result") or {}).get("summary", ""),
        }

    if not doc:
        raise HTTPException(status_code=404, detail="报告内容不存在")

    stock_symbol = doc.get("stock_symbol", "unknown")
    analysis_date = doc.get("analysis_date", datetime.now().strftime("%Y-%m-%d"))

    if format == "markdown":
        from app.utils.report_exporter import report_exporter
        content = report_exporter.generate_markdown_report(doc)
        filename = f"{stock_symbol}_{analysis_date}_report.md"

        def generate():
            yield content.encode("utf-8")

        return StreamingResponse(
            generate(),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    if format == "pdf":
        from app.utils.report_exporter import report_exporter
        if not report_exporter.pandoc_available:
            raise HTTPException(status_code=400, detail="PDF 导出不可用，请安装 pandoc")
        pdf_content = report_exporter.generate_pdf_report(doc)
        filename = f"{stock_symbol}_{analysis_date}_report.pdf"

        def generate():
            yield pdf_content

        return StreamingResponse(
            generate(),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    if format == "docx":
        from app.utils.report_exporter import report_exporter
        if not report_exporter.pandoc_available:
            raise HTTPException(status_code=400, detail="Word 导出不可用，请安装 pandoc")
        docx_content = report_exporter.generate_docx_report(doc)
        filename = f"{stock_symbol}_{analysis_date}_report.docx"

        def generate():
            yield docx_content

        return StreamingResponse(
            generate(),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    raise HTTPException(status_code=400, detail=f"不支持的格式: {format}")
