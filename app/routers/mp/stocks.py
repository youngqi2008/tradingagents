"""小程序行情 / K 线 API（个股 + 主要指数）"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.database import get_mongo_db
from app.core.response import ok
from app.routers.mp.deps import get_current_mp_user
from app.routers.stocks import get_kline, get_quote

router = APIRouter(prefix="/stocks", tags=["mp-stocks"])
logger = logging.getLogger("webapi")

# 指数：对外统一用新浪风格代码（sh000001）
INDEX_META: Dict[str, Dict[str, str]] = {
    "sh000001": {"name": "上证指数", "ts_code": "000001.SH", "alias": ("沪指", "上证", "上证指数")},
    "sz399001": {"name": "深证成指", "ts_code": "399001.SZ", "alias": ("深成指", "深证成指")},
    "sz399006": {"name": "创业板指", "ts_code": "399006.SZ", "alias": ("创业板指", "创指")},
    "sh000300": {"name": "沪深300", "ts_code": "000300.SH", "alias": ("沪深300", "沪深三百")},
    "sh000016": {"name": "上证50", "ts_code": "000016.SH", "alias": ("上证50",)},
    "sh000688": {"name": "科创50", "ts_code": "000688.SH", "alias": ("科创50",)},
}


def _normalize_index_code(code: str) -> Optional[str]:
    """识别指数代码/别名，返回标准 sh/sz 代码；非指数返回 None。"""
    raw = (code or "").strip()
    if not raw:
        return None
    key = raw.lower().replace(" ", "")
    if key in INDEX_META:
        return key
    upper = raw.upper()
    for std, meta in INDEX_META.items():
        if upper == meta["ts_code"]:
            return std
        if raw in meta.get("alias", ()):
            return std
    # 000001.SH / 399001.SZ
    if "." in upper:
        num, mkt = upper.split(".", 1)
        if mkt == "SH" and f"sh{num.zfill(6)}" in INDEX_META:
            return f"sh{num.zfill(6)}"
        if mkt == "SZ" and f"sz{num.zfill(6)}" in INDEX_META:
            return f"sz{num.zfill(6)}"
    return None


def _index_secid(symbol: str) -> Optional[str]:
    """东财 secid：沪市 1.xxxxxx，深市 0.xxxxxx。"""
    s = (symbol or "").lower()
    if s.startswith("sh") and len(s) >= 8:
        return f"1.{s[2:8]}"
    if s.startswith("sz") and len(s) >= 8:
        return f"0.{s[2:8]}"
    return None


def _resample_ohlc(items: List[dict], period: str) -> List[dict]:
    """从日线重采样周/月线。"""
    if period == "day" or not items:
        return items
    import pandas as pd

    df = pd.DataFrame(items)
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df = df.dropna(subset=["time"]).sort_values("time")
    if df.empty:
        return []
    df = df.set_index("time")
    rule = "W-FRI" if period == "week" else "M"
    agg = df.resample(rule).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "amount": "sum",
    }).dropna(subset=["open", "close"])
    out = []
    for ts, row in agg.iterrows():
        vol = row.get("volume")
        amt = row.get("amount")
        out.append({
            "time": ts.strftime("%Y-%m-%d"),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(vol) if vol == vol else None,
            "amount": float(amt) if amt == amt else None,
        })
    return out


def _df_to_index_bars(df) -> List[dict]:
    """将各数据源 DataFrame 统一成 bars。"""
    if df is None or getattr(df, "empty", True):
        return []
    col_map = {}
    for c in df.columns:
        cl = str(c).lower()
        if c in ("date", "日期") or "date" in cl or c == "day":
            col_map[c] = "time"
        elif c in ("open", "开盘"):
            col_map[c] = "open"
        elif c in ("high", "最高"):
            col_map[c] = "high"
        elif c in ("low", "最低"):
            col_map[c] = "low"
        elif c in ("close", "收盘"):
            col_map[c] = "close"
        elif c in ("volume", "成交量", "vol"):
            col_map[c] = "volume"
        elif c in ("amount", "成交额"):
            col_map[c] = "amount"
    df = df.rename(columns=col_map)
    if "time" not in df.columns or "close" not in df.columns:
        return []

    items = []
    for _, row in df.iterrows():
        t = row.get("time")
        try:
            if hasattr(t, "strftime"):
                time_str = t.strftime("%Y-%m-%d")
            else:
                time_str = str(t)[:10]
            items.append({
                "time": time_str,
                "open": float(row.get("open") or 0),
                "high": float(row.get("high") or 0),
                "low": float(row.get("low") or 0),
                "close": float(row.get("close") or 0),
                "volume": float(row["volume"]) if row.get("volume") is not None else None,
                "amount": float(row["amount"]) if row.get("amount") is not None else None,
            })
        except Exception:
            continue
    items.sort(key=lambda x: x["time"])
    return items


def _fetch_em_index_kline_direct(symbol: str, limit: int) -> List[dict]:
    """直连东财历史 K 线（trust_env=False，避开系统 HTTP_PROXY）。"""
    import requests

    secid = _index_secid(symbol)
    if not secid:
        return []
    # 多拉一些，便于周/月重采样
    lmt = max(int(limit or 120) * 3, 300)
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        "klt": 101,
        "fqt": 0,
        "beg": "19900101",
        "end": "20500101",
        "lmt": lmt,
    }
    session = requests.Session()
    session.trust_env = False  # 不走 HTTP(S)_PROXY，国内行情源常被代理打断
    resp = session.get(url, params=params, timeout=15)
    resp.raise_for_status()
    payload = resp.json() or {}
    klines = ((payload.get("data") or {}).get("klines")) or []
    items = []
    for line in klines:
        parts = str(line).split(",")
        if len(parts) < 6:
            continue
        try:
            items.append({
                "time": parts[0][:10],
                "open": float(parts[1]),
                "close": float(parts[2]),
                "high": float(parts[3]),
                "low": float(parts[4]),
                "volume": float(parts[5]) if parts[5] not in ("", "-") else None,
                "amount": float(parts[6]) if len(parts) > 6 and parts[6] not in ("", "-") else None,
            })
        except Exception:
            continue
    return items


def _load_index_kline_cache(symbol: str) -> List[dict]:
    try:
        from app.core.database import get_mongo_db_sync

        db = get_mongo_db_sync()
        doc = db.mp_index_kline.find_one({"code": symbol}, {"_id": 0, "items": 1})
        items = (doc or {}).get("items") or []
        return items if isinstance(items, list) else []
    except Exception as e:
        logger.warning(f"读取指数K线缓存失败 {symbol}: {e}")
        return []


def _save_index_kline_cache(symbol: str, items: List[dict]) -> None:
    if not items:
        return
    try:
        from app.core.database import get_mongo_db_sync

        db = get_mongo_db_sync()
        # 最多保留约 3 年日线，控制文档体积
        keep = items[-800:] if len(items) > 800 else items
        db.mp_index_kline.update_one(
            {"code": symbol},
            {
                "$set": {
                    "code": symbol,
                    "items": keep,
                    "updated_at": datetime.utcnow(),
                    "count": len(keep),
                }
            },
            upsert=True,
        )
    except Exception as e:
        logger.warning(f"写入指数K线缓存失败 {symbol}: {e}")


def _fetch_index_kline_sync(symbol: str, period: str, limit: int) -> List[dict]:
    """拉指数日线（多源 + Mongo 缓存），必要时重采样周/月。"""
    import akshare as ak

    items: List[dict] = []
    source = ""

    # 1) 新浪（akshare）
    try:
        df = ak.stock_zh_index_daily(symbol=symbol)
        items = _df_to_index_bars(df)
        if items:
            source = "sina"
    except Exception as e:
        logger.warning(f"stock_zh_index_daily 失败 {symbol}: {e}")

    # 2) 东财 akshare（可能被 HTTP_PROXY 打断）
    if not items:
        try:
            df = ak.stock_zh_index_daily_em(symbol=symbol)
            items = _df_to_index_bars(df)
            if items:
                source = "eastmoney_ak"
        except Exception as e:
            logger.warning(f"stock_zh_index_daily_em 失败 {symbol}: {e}")

    # 3) 东财直连（绕过代理）——盘后/代理异常时的主兜底
    if not items:
        try:
            items = _fetch_em_index_kline_direct(symbol, limit)
            if items:
                source = "eastmoney_direct"
        except Exception as e:
            logger.warning(f"eastmoney_direct 指数K线失败 {symbol}: {e}")

    # 4) Mongo 上次成功缓存（盘后外部源全挂仍可看）
    if not items:
        cached = _load_index_kline_cache(symbol)
        if cached:
            items = cached
            source = "mongo_cache"
            logger.info(f"指数K线使用缓存 {symbol} bars={len(items)}")

    if not items:
        return []

    if source and source != "mongo_cache":
        _save_index_kline_cache(symbol, items)
        logger.info(f"指数K线获取成功 {symbol} source={source} bars={len(items)}")

    items = _resample_ohlc(items, period)
    if limit and len(items) > limit:
        items = items[-limit:]
    return items


def _fetch_index_quote_sync(symbol: str, name: str) -> dict:
    """指数实时行情（新浪现货表）。"""
    import akshare as ak

    price = open_ = high = low = prev = amount = volume = pct = None
    try:
        df = ak.stock_zh_index_spot_sina()
        if df is not None and not df.empty:
            row = df[df["代码"] == symbol]
            if row.empty:
                row = df[df["代码"].astype(str).str.contains(symbol[-6:], na=False)]
            if not row.empty:
                r = row.iloc[0]
                price = float(r.get("最新价") or 0)
                open_ = float(r.get("今开") or 0)
                high = float(r.get("最高") or 0)
                low = float(r.get("最低") or 0)
                prev = float(r.get("昨收") or 0)
                amount = float(r.get("成交额") or 0)
                volume = float(r.get("成交量") or 0)
                pct = float(r.get("涨跌幅") or 0)
                name = str(r.get("名称") or name)
    except Exception as e:
        logger.warning(f"指数现货行情失败 {symbol}: {e}")

    # 现货失败则用日线最后一根近似
    if price is None:
        bars = _fetch_index_kline_sync(symbol, "day", 2)
        if bars:
            last = bars[-1]
            price = last["close"]
            open_ = last["open"]
            high = last["high"]
            low = last["low"]
            amount = last.get("amount")
            volume = last.get("volume")
            if len(bars) >= 2 and bars[-2]["close"]:
                prev = bars[-2]["close"]
                pct = round((price - prev) / prev * 100, 2)

    return {
        "code": symbol,
        "name": name,
        "market": "CN",
        "price": price,
        "change_percent": pct,
        "open": open_,
        "high": high,
        "low": low,
        "prev_close": prev,
        "amount": amount,
        "volume": volume,
        "trade_date": datetime.now().strftime("%Y-%m-%d"),
        "is_index": True,
    }


@router.get("/search")
async def mp_search_stocks(
    q: str = Query(..., min_length=1, description="股票代码或名称"),
    limit: int = Query(10, ge=1, le=30),
    user: dict = Depends(get_current_mp_user),
):
    """搜索股票（代码 / 名称）；支持沪指等指数别名"""
    keyword = q.strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="请输入搜索关键词")

    items = []
    seen = set()

    # 指数优先匹配
    idx = _normalize_index_code(keyword)
    if idx:
        meta = INDEX_META[idx]
        items.append({"code": idx, "name": meta["name"], "market": "CN", "is_index": True})
        seen.add(idx)
    else:
        kw_lower = keyword.lower()
        for std, meta in INDEX_META.items():
            if keyword in meta["alias"] or kw_lower in std or meta["name"].find(keyword) >= 0:
                if std not in seen:
                    items.append({"code": std, "name": meta["name"], "market": "CN", "is_index": True})
                    seen.add(std)

    db = get_mongo_db()
    conditions = []
    if keyword.isdigit():
        conditions.append({"code": {"$regex": f"^{keyword}"}})
        conditions.append({"symbol": {"$regex": f"^{keyword}"}})
    else:
        conditions.append({"name": {"$regex": keyword, "$options": "i"}})
        if any(c.isdigit() for c in keyword):
            conditions.append({"code": {"$regex": keyword}})
            conditions.append({"symbol": {"$regex": keyword}})

    if conditions:
        cursor = db.stock_basic_info.find(
            {"$or": conditions},
            {"_id": 0, "code": 1, "symbol": 1, "name": 1, "market": 1},
        ).limit(limit * 3)
        async for doc in cursor:
            raw = str(doc.get("code") or doc.get("symbol") or "").strip()
            if not raw:
                continue
            code = raw.zfill(6) if raw.isdigit() else raw.upper()
            if code in seen:
                continue
            seen.add(code)
            items.append({
                "code": code,
                "name": doc.get("name") or code,
                "market": doc.get("market") or "CN",
                "is_index": False,
            })
            if len(items) >= limit:
                break

    return ok(data={"items": items[:limit], "keyword": keyword})


@router.get("/{code}/quote")
async def mp_get_quote(
    code: str,
    force_refresh: bool = Query(False),
    user: dict = Depends(get_current_mp_user),
):
    """获取实时行情；指数走专用数据源"""
    idx = _normalize_index_code(code)
    if idx:
        meta = INDEX_META[idx]
        try:
            data = await asyncio.to_thread(_fetch_index_quote_sync, idx, meta["name"])
            return ok(data=data)
        except Exception as e:
            logger.exception("指数行情失败")
            raise HTTPException(status_code=500, detail=f"获取指数行情失败: {e}")
    return await get_quote(code=code, force_refresh=force_refresh, current_user=user)


@router.get("/{code}/kline")
async def mp_get_kline(
    code: str,
    period: str = Query("day", description="day/week/month"),
    limit: int = Query(120, ge=10, le=500),
    adj: str = Query("none", description="none/qfq/hfq"),
    force_refresh: bool = Query(False),
    user: dict = Depends(get_current_mp_user),
):
    """获取 K 线；默认沪指等指数走 AKShare 指数接口"""
    if period not in ("day", "week", "month", "5m", "15m", "30m", "60m"):
        raise HTTPException(status_code=400, detail=f"不支持的period: {period}")

    idx = _normalize_index_code(code)
    if idx:
        if period not in ("day", "week", "month"):
            raise HTTPException(status_code=400, detail="指数仅支持日/周/月K")
        try:
            items = await asyncio.to_thread(_fetch_index_kline_sync, idx, period, limit)
            if not items:
                raise HTTPException(status_code=404, detail="未获取到指数K线数据")
            return ok(data={
                "code": idx,
                "name": INDEX_META[idx]["name"],
                "period": period,
                "items": items,
                "source": "akshare_index",
                "is_index": True,
            })
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("指数K线失败")
            raise HTTPException(status_code=500, detail=f"获取指数K线失败: {e}")

    return await get_kline(
        code=code,
        period=period,
        limit=limit,
        adj=adj,
        force_refresh=force_refresh,
        current_user=user,
    )
