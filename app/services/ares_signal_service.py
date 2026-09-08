"""外部买卖点信号 → 小程序站内通知"""

import re
from typing import Optional, Tuple

from app.models.ares_signal import AresSignalParsed, AresSignalWebhook
from app.models.mp_notification import MpNotificationCreate, MpNotificationResponse
from app.services.mp_notification_service import mp_notification_service

try:
    from tradingagents.utils.logging_manager import get_logger
except ImportError:
    import logging

    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)

logger = get_logger("ares_signal_service")

BUY_TAG = "[关注]"
SELL_TAG = "[取消关注]"
STOCK_RE = re.compile(r"(\d{6})\.([A-Z]+)")
TIME_RE = re.compile(r"时间:\s*(.+?)(?:\n|$)")


class AresSignalService:
    def parse_webhook(self, payload: AresSignalWebhook) -> AresSignalParsed:
        content = (payload.text.content or "").strip()
        if not content:
            raise ValueError("text.content 不能为空")

        if BUY_TAG in content:
            signal_type = "buy"
        elif SELL_TAG in content:
            signal_type = "sell"
        else:
            raise ValueError("content 须包含 [关注] 或 [取消关注]")

        stock_match = STOCK_RE.search(content)
        if not stock_match:
            raise ValueError("未识别股票代码，格式示例：600378.SSE")

        time_match = TIME_RE.search(content)
        return AresSignalParsed(
            signal_type=signal_type,
            stock_code=stock_match.group(1),
            market=stock_match.group(2),
            signal_time=time_match.group(1).strip() if time_match else None,
            raw_content=content,
        )

    def _build_notification(self, parsed: AresSignalParsed) -> Tuple[str, str, str]:
        if parsed.signal_type == "buy":
            title = f"服务动态 · {parsed.stock_code}"
            notice_type = "buy_signal"
        else:
            title = f"服务更新 · {parsed.stock_code}"
            notice_type = "sell_signal"

        lines = [parsed.raw_content]
        if parsed.market:
            lines.append(f"分类: {parsed.market}")
        lines.append(f"编号: {parsed.stock_code}")
        content = "\n".join(lines)
        return title, content, notice_type

    async def push_to_miniprogram(
        self, payload: AresSignalWebhook
    ) -> MpNotificationResponse:
        parsed = self.parse_webhook(payload)
        title, content, notice_type = self._build_notification(parsed)
        data = MpNotificationCreate(
            title=title,
            content=content,
            notice_type=notice_type,
            target_type="all",
        )
        result = await mp_notification_service.create_notification(
            data, created_by="ares_signal"
        )
        logger.info(
            "买卖点信号已推送 type=%s code=%s notification_id=%s recipients=%s",
            parsed.signal_type,
            parsed.stock_code,
            result.id,
            result.recipient_count,
        )
        return result


ares_signal_service = AresSignalService()
