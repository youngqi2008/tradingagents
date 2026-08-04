"""
A 股大盘复盘（移植自 daily_stock_analysis 下午定时企微推送）

流程：采集指数/涨跌统计/板块 → 生成复盘文案 → 推送全体小程序用户站内信
默认工作日 18:00（与 DSA SCHEDULE_TIME 一致）
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Tuple

from app.models.mp_notification import MpNotificationCreate
from app.services.mp_notification_service import mp_notification_service
from app.utils.timezone import now_tz

try:
    from tradingagents.utils.logging_manager import get_logger
except ImportError:
    import logging

    def get_logger(name: str):
        return logging.getLogger(name)

logger = get_logger("market_review_service")

INDICES_MAP = {
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
    "sh000300": "沪深300",
    "sh000016": "上证50",
    "sh000688": "科创50",
}


def _safe_float(v, default: float = 0.0) -> float:
    try:
        if v is None or v == "" or v == "-":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _fetch_indices_sync() -> List[Dict[str, Any]]:
    import akshare as ak

    df = ak.stock_zh_index_spot_sina()
    results: List[Dict[str, Any]] = []
    if df is None or df.empty:
        return results
    for code, name in INDICES_MAP.items():
        row = df[df["代码"] == code]
        if row.empty:
            row = df[df["代码"].astype(str).str.contains(code[-6:], na=False)]
        if row.empty:
            continue
        r = row.iloc[0]
        current = _safe_float(r.get("最新价"))
        prev = _safe_float(r.get("昨收"))
        high = _safe_float(r.get("最高"))
        low = _safe_float(r.get("最低"))
        amp = ((high - low) / prev * 100) if prev > 0 else 0.0
        results.append(
            {
                "code": code,
                "name": name,
                "current": current,
                "change": _safe_float(r.get("涨跌额")),
                "change_pct": _safe_float(r.get("涨跌幅")),
                "open": _safe_float(r.get("今开")),
                "high": high,
                "low": low,
                "prev_close": prev,
                "amount": _safe_float(r.get("成交额")),
                "volume": _safe_float(r.get("成交量")),
                "amplitude": amp,
            }
        )
    return results


def _fetch_market_stats_sync() -> Dict[str, Any]:
    import akshare as ak
    import pandas as pd

    df = None
    try:
        df = ak.stock_zh_a_spot_em()
    except Exception as e:
        logger.warning("东财全市场行情失败，尝试新浪: %s", e)
        try:
            df = ak.stock_zh_a_spot()
        except Exception as e2:
            logger.error("新浪全市场行情失败: %s", e2)
            return {}

    if df is None or df.empty:
        return {}

    pct_col = next((c for c in ("涨跌幅", "changepercent", "涨幅") if c in df.columns), None)
    amount_col = next((c for c in ("成交额", "amount") if c in df.columns), None)
    if not pct_col:
        return {}

    pct = pd.to_numeric(df[pct_col], errors="coerce")
    amount = pd.to_numeric(df[amount_col], errors="coerce") if amount_col else None
    valid = pct.dropna()
    up = int((valid > 0).sum())
    down = int((valid < 0).sum())
    flat = int((valid == 0).sum())
    # 近似涨跌停（主板约 ±10%）
    limit_up = int((valid >= 9.7).sum())
    limit_down = int((valid <= -9.7).sum())
    total_amount = 0.0
    if amount is not None:
        # 东财成交额多为元
        total_amount = float(amount.fillna(0).sum()) / 1e8

    return {
        "up_count": up,
        "down_count": down,
        "flat_count": flat,
        "limit_up_count": limit_up,
        "limit_down_count": limit_down,
        "total_amount": total_amount,
    }


def _fetch_sector_rankings_sync(n: int = 5) -> Tuple[List[Dict], List[Dict]]:
    import akshare as ak
    import pandas as pd

    try:
        df = ak.stock_board_industry_name_em()
    except Exception as e:
        logger.warning("板块排行失败: %s", e)
        return [], []
    if df is None or df.empty or "涨跌幅" not in df.columns:
        return [], []
    df = df.copy()
    df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
    df = df.dropna(subset=["涨跌幅"])
    name_col = "板块名称" if "板块名称" in df.columns else df.columns[0]
    top = df.nlargest(n, "涨跌幅")
    bottom = df.nsmallest(n, "涨跌幅")
    top_sectors = [{"name": str(r[name_col]), "change_pct": float(r["涨跌幅"])} for _, r in top.iterrows()]
    bottom_sectors = [
        {"name": str(r[name_col]), "change_pct": float(r["涨跌幅"])} for _, r in bottom.iterrows()
    ]
    return top_sectors, bottom_sectors


def _build_template_report(
    date_str: str,
    indices: List[Dict[str, Any]],
    stats: Dict[str, Any],
    top_sectors: List[Dict],
    bottom_sectors: List[Dict],
) -> str:
    mood_index = next((i for i in indices if i["code"] == "sh000001"), None)
    if mood_index:
        pct = mood_index.get("change_pct") or 0
        if pct > 1:
            market_mood = "强势上涨"
        elif pct > 0:
            market_mood = "小幅上涨"
        elif pct > -1:
            market_mood = "小幅下跌"
        else:
            market_mood = "明显下跌"
    else:
        market_mood = "震荡整理"

    indices_text = ""
    for idx in indices[:6]:
        pct = idx.get("change_pct") or 0
        direction = "↑" if pct > 0 else "↓" if pct < 0 else "-"
        indices_text += (
            f"- **{idx['name']}**: {idx.get('current', 0):.2f} "
            f"({direction}{abs(pct):.2f}%)\n"
        )

    top_text = "、".join([s["name"] for s in (top_sectors or [])[:3]]) or "—"
    bottom_text = "、".join([s["name"] for s in (bottom_sectors or [])[:3]]) or "—"

    up = stats.get("up_count", 0)
    down = stats.get("down_count", 0)
    limit_up = stats.get("limit_up_count", 0)
    limit_down = stats.get("limit_down_count", 0)
    amount = stats.get("total_amount", 0.0)

    report = f"""🎯 大盘复盘 · {date_str}

### 一、市场总结
今日市场整体呈「{market_mood}」格局。上涨 {up} 家，下跌 {down} 家；涨停约 {limit_up}，跌停约 {limit_down}；两市成交额约 {amount:.0f} 亿元。

### 二、主要指数
{indices_text or '- （暂无指数数据）'}

### 三、涨跌统计
| 指标 | 数值 |
|------|------|
| 上涨家数 | {up} |
| 下跌家数 | {down} |
| 平盘 | {stats.get('flat_count', 0)} |
| 涨停(约) | {limit_up} |
| 跌停(约) | {limit_down} |
| 两市成交额 | {amount:.0f}亿 |

### 四、板块表现
- **领涨**: {top_text}
- **领跌**: {bottom_text}

### 五、风险提示
市场有风险，投资需谨慎。以上数据仅供参考，不构成投资建议。

---
*复盘时间: {now_tz().strftime('%H:%M')} · Ares*
"""
    return report.strip()


class MarketReviewService:
    async def collect_overview(self) -> Dict[str, Any]:
        indices = await asyncio.to_thread(_fetch_indices_sync)
        stats = await asyncio.to_thread(_fetch_market_stats_sync)
        top, bottom = await asyncio.to_thread(_fetch_sector_rankings_sync, 5)
        return {
            "date": now_tz().strftime("%Y-%m-%d"),
            "indices": indices,
            "stats": stats or {},
            "top_sectors": top or [],
            "bottom_sectors": bottom or [],
        }

    def build_report(self, overview: Dict[str, Any]) -> str:
        return _build_template_report(
            overview.get("date") or now_tz().strftime("%Y-%m-%d"),
            overview.get("indices") or [],
            overview.get("stats") or {},
            overview.get("top_sectors") or [],
            overview.get("bottom_sectors") or [],
        )

    async def run_and_push(
        self,
        *,
        created_by: str = "system:market_review",
        push: bool = True,
    ) -> Dict[str, Any]:
        """生成大盘复盘并推送给全体小程序用户。"""
        logger.info("开始大盘复盘...")
        overview = await self.collect_overview()
        report = self.build_report(overview)
        if not overview.get("indices") and not overview.get("stats"):
            logger.warning("大盘复盘数据采集为空，仍将推送模板提示")

        notification_id = None
        if push:
            title = f"大盘复盘 · {now_tz().strftime('%m-%d')}"
            # 站内信内容控制长度
            content = report if len(report) <= 12000 else (report[:11900] + "\n…")
            n = await mp_notification_service.create_notification(
                MpNotificationCreate(
                    title=title,
                    content=content,
                    notice_type="market_review",
                    target_type="all",
                ),
                created_by=created_by,
            )
            notification_id = n.id
            logger.info("大盘复盘已推送全体小程序用户 notification_id=%s", notification_id)

        return {
            "date": overview.get("date"),
            "indices_count": len(overview.get("indices") or []),
            "up_count": (overview.get("stats") or {}).get("up_count", 0),
            "down_count": (overview.get("stats") or {}).get("down_count", 0),
            "notification_id": notification_id,
            "report_preview": report[:400],
            "ran_at": now_tz().isoformat(),
        }


market_review_service = MarketReviewService()
