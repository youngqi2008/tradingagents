"""
自选股日报推送（替代 daily_stock_analysis 的企业微信 STOCK_LIST 推送）

逻辑：
1. 按每位小程序用户的自选股分别生成日报
2. 推送到小程序站内信（mp_notifications，target=users），不发企业微信
"""

from __future__ import annotations

from datetime import timedelta
from html import unescape
from typing import Any, Dict, List, Optional
import re

from app.core.database import get_mongo_db
from app.models.mp_notification import MpNotificationCreate
from app.services.favorites_service import favorites_service
from app.services.mp_notification_service import mp_notification_service
from app.utils.timezone import now_tz

try:
    from tradingagents.utils.logging_manager import get_logger
except ImportError:
    import logging

    def get_logger(name: str):
        return logging.getLogger(name)

logger = get_logger("favorites_digest_service")


class FavoritesDigestService:
    async def _quotes_map(self, codes: List[str]) -> Dict[str, dict]:
        if not codes:
            return {}
        db = get_mongo_db()
        cursor = db["market_quotes"].find(
            {"code": {"$in": codes}},
            {"code": 1, "close": 1, "pct_chg": 1, "name": 1},
        )
        docs = await cursor.to_list(length=None)
        return {str(d.get("code")).zfill(6): d for d in (docs or [])}

    async def _news_headlines(self, code: str, limit: int = 2) -> List[str]:
        db = get_mongo_db()
        since = now_tz() - timedelta(days=3)
        cursor = (
            db["stock_news"]
            .find(
                {
                    "$or": [{"symbol": code}, {"code": code}],
                    "publish_time": {"$gte": since},
                },
                {"title": 1, "publish_time": 1},
            )
            .sort("publish_time", -1)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        if not docs:
            # 兼容无 publish_time 过滤
            cursor = (
                db["stock_news"]
                .find({"$or": [{"symbol": code}, {"code": code}]}, {"title": 1})
                .sort([("publish_time", -1), ("_id", -1)])
                .limit(limit)
            )
            docs = await cursor.to_list(length=limit)
        out = []
        for d in docs or []:
            t = (d.get("title") or "").strip()
            if t:
                t = re.sub(r"<[^>]+>", "", unescape(t)).strip()
                out.append(t[:60])
        return out

    def _fmt_pct(self, v) -> str:
        try:
            n = float(v)
            sign = "+" if n > 0 else ""
            return f"{sign}{n:.2f}%"
        except (TypeError, ValueError):
            return "-"

    def _fmt_price(self, v) -> str:
        try:
            return f"{float(v):.2f}"
        except (TypeError, ValueError):
            return "-"

    async def build_user_digest(self, favorites: List[Dict[str, Any]]) -> str:
        codes = []
        for f in favorites:
            c = f.get("stock_code")
            if not c:
                continue
            codes.append(str(c).zfill(6) if str(c).isdigit() else str(c))
        quotes = await self._quotes_map(codes)
        today = now_tz().strftime("%Y-%m-%d")
        lines = [f"【自选股日报】{today}", ""]
        for f in favorites:
            code = f.get("stock_code") or ""
            if str(code).isdigit():
                code = str(code).zfill(6)
            name = f.get("stock_name") or quotes.get(code, {}).get("name") or code
            q = quotes.get(code) or {}
            price = self._fmt_price(q.get("close"))
            pct = self._fmt_pct(q.get("pct_chg"))
            lines.append(f"• {code} {name}")
            lines.append(f"  现价 {price}  涨跌 {pct}")
            news = await self._news_headlines(code, limit=2)
            if news:
                for n in news:
                    lines.append(f"  资讯：{n}")
            else:
                lines.append("  资讯：暂无近3日入库新闻")
            lines.append("")
        lines.append("以上为您订阅自选股的行情与资讯摘要，不构成投资建议。")
        return "\n".join(lines).strip()

    async def run_daily_digest(
        self,
        *,
        user_id: Optional[str] = None,
        created_by: str = "system:favorites_digest",
    ) -> Dict[str, Any]:
        """
        为每位有自选的小程序用户各推送一份站内信。

        隔离保证：
        - 内容只来自该用户自己的自选（循环内二次读取 mp:{uid}）
        - 通知 target_type 固定为 users，target_user_ids 仅含该 uid（绝不全员）
        """
        mapping = await favorites_service.list_mp_favorites_by_user()
        if user_id:
            uid = int(user_id) if str(user_id).isdigit() else None
            mapping = {uid: mapping[uid]} if uid and uid in mapping else {}

        sent = 0
        skipped = 0
        errors: List[str] = []
        for uid in list(mapping.keys()):
            # 二次读取：只信该用户命名空间下的自选，避免误用他人列表
            key = favorites_service.mp_user_key(uid)
            try:
                favs = await favorites_service.get_user_favorites(key)
            except Exception as e:
                errors.append(f"user={uid} load: {e}")
                logger.exception("读取用户自选失败 user=%s", uid)
                continue

            favs = [f for f in (favs or []) if f.get("stock_code")]
            if not favs:
                skipped += 1
                continue

            codes = [
                str(f["stock_code"]).zfill(6)
                if str(f["stock_code"]).isdigit()
                else str(f["stock_code"])
                for f in favs
            ]
            try:
                content = await self.build_user_digest(favs)
                title = f"自选股日报 · {now_tz().strftime('%m-%d')}（{len(favs)}只）"
                # 强制单用户定向：禁止 all / membership
                await mp_notification_service.create_notification(
                    MpNotificationCreate(
                        title=title,
                        content=content,
                        notice_type="favorites_digest",
                        target_type="users",
                        target_user_ids=[str(uid)],
                    ),
                    created_by=created_by,
                )
                sent += 1
                logger.info(
                    "自选日报已定向推送 user=%s stocks=%s count=%s",
                    uid,
                    ",".join(codes),
                    len(codes),
                )
            except Exception as e:
                msg = f"user={uid}: {e}"
                logger.exception("自选日报推送失败 %s", msg)
                errors.append(msg)

        result = {
            "users_total": len(mapping),
            "sent": sent,
            "skipped": skipped,
            "errors": errors,
            "ran_at": now_tz().isoformat(),
            "isolation": "per_user_favorites_only",
        }
        logger.info("自选日报推送完成: %s", result)
        return result


favorites_digest_service = FavoritesDigestService()
