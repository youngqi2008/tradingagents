"""小程序财经新闻 API"""

import re
from datetime import datetime, timedelta
from html import unescape
from typing import Any, Dict, List, Set

from fastapi import APIRouter, Depends, Query

from app.core.response import ok
from app.core.database import get_mongo_db
from app.routers.mp.deps import get_current_mp_user
from app.services.favorites_service import favorites_service
from app.utils.timezone import now_tz

router = APIRouter(prefix="/news", tags=["mp-news"])

_TAG_RE = re.compile(r"<[^>]+>")


def _clean_text(text: Any) -> str:
    """去掉东财等源标题里的 <em> 等 HTML 标签与实体。"""
    if text is None:
        return ""
    s = unescape(str(text))
    s = _TAG_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _norm_code(code: Any) -> str:
    s = str(code or "").strip()
    if not s:
        return ""
    # 600519.SH / sh600519
    if "." in s:
        s = s.split(".", 1)[0]
    s = s.lower()
    if s.startswith(("sh", "sz", "bj")) and len(s) > 2:
        s = s[2:]
    if s.isdigit():
        return s.zfill(6)
    return s.upper()


def _codes_from_news(doc: dict) -> List[str]:
    codes: List[str] = []
    for key in ("symbol", "code"):
        c = _norm_code(doc.get(key))
        if c and c not in codes:
            codes.append(c)
    for item in doc.get("symbols") or []:
        if isinstance(item, dict):
            c = _norm_code(item.get("code") or item.get("symbol"))
        else:
            c = _norm_code(item)
        if c and c not in codes:
            codes.append(c)
    return codes


def _fmt_time(v) -> str:
    if not v:
        return ""
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)


@router.get("/latest")
async def mp_latest_news(
    hours: int = Query(72, ge=1, le=168, description="回溯小时数"),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
    favorites_first: bool = Query(True, description="自选相关新闻排前"),
    user: dict = Depends(get_current_mp_user),
):
    """
    最新财经新闻（来自 Mongo stock_news）。
    若新闻关联股票在用户自选中，标记 is_favorite / highlight，并可优先排序。
    """
    fav_codes: Set[str] = set()
    try:
        key = favorites_service.mp_user_key(user["id"])
        favs = await favorites_service.get_user_favorites(key)
        for f in favs or []:
            c = _norm_code(f.get("stock_code"))
            if c:
                fav_codes.add(c)
    except Exception:
        fav_codes = set()

    db = get_mongo_db()
    since = now_tz() - timedelta(hours=hours)
    # 多取一些再本地排序，保证自选加权后仍够 limit
    fetch_limit = min(300, max(limit * 3, limit + skip))
    query = {
        "$or": [
            {"publish_time": {"$gte": since}},
            {"publish_time": {"$gte": since.replace(tzinfo=None)}},
        ]
    }
    cursor = (
        db["stock_news"]
        .find(query)
        .sort([("publish_time", -1), ("_id", -1)])
        .limit(fetch_limit)
    )
    docs = await cursor.to_list(length=fetch_limit)

    # 若带时区查询为空，退化为不限时间取最新
    if not docs:
        cursor = db["stock_news"].find({}).sort([("publish_time", -1), ("_id", -1)]).limit(fetch_limit)
        docs = await cursor.to_list(length=fetch_limit)

    items: List[Dict[str, Any]] = []
    seen = set()
    for doc in docs or []:
        title = _clean_text(doc.get("title"))
        if not title:
            continue
        # 去重：同标题+主代码
        codes = _codes_from_news(doc)
        dedupe_key = (title, codes[0] if codes else "")
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        matched = [c for c in codes if c in fav_codes]
        is_fav = len(matched) > 0
        full_content = _clean_text(doc.get("content") or doc.get("summary") or "")
        # 列表预览与详情正文分离，避免前端只能看到截断摘要
        preview = full_content[:200]
        if len(full_content) > 200:
            preview = preview.rstrip() + "…"
        items.append(
            {
                "id": str(doc.get("_id") or ""),
                "title": title,
                "summary": preview,
                "content": full_content[:8000],
                "source": doc.get("source") or doc.get("data_source") or "",
                "url": doc.get("url") or doc.get("link") or "",
                "publish_time": _fmt_time(doc.get("publish_time")),
                "symbols": codes,
                "symbol": codes[0] if codes else "",
                "stock_name": doc.get("stock_name") or doc.get("name") or "",
                "is_favorite": is_fav,
                "highlight": is_fav,
                "favorite_symbols": matched,
            }
        )

    if favorites_first:
        fav_items = [x for x in items if x.get("is_favorite")]
        other = [x for x in items if not x.get("is_favorite")]
        fav_items.sort(key=lambda x: x.get("publish_time") or "", reverse=True)
        other.sort(key=lambda x: x.get("publish_time") or "", reverse=True)
        items = fav_items + other
    else:
        items.sort(key=lambda x: x.get("publish_time") or "", reverse=True)

    page = items[skip : skip + limit]
    return ok(
        data={
            "items": page,
            "total": len(items),
            "favorite_count": sum(1 for x in items if x.get("is_favorite")),
            "hours": hours,
            "favorite_codes": sorted(fav_codes),
        }
    )
