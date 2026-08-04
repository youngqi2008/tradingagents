"""买卖点信号解析单元测试"""

import pytest

from app.models.ares_signal import AresSignalWebhook
from app.services.ares_signal_service import ares_signal_service


def test_parse_buy_signal():
    payload = AresSignalWebhook(
        msgtype="text",
        text={"content": "[关注] 600378.SSE\n时间: 2026-07-11 10:15:04"},
    )
    parsed = ares_signal_service.parse_webhook(payload)
    assert parsed.signal_type == "buy"
    assert parsed.stock_code == "600378"
    assert parsed.market == "SSE"
    assert parsed.signal_time == "2026-07-11 10:15:04"


def test_parse_sell_signal():
    payload = AresSignalWebhook(
        msgtype="text",
        text={"content": "[取消关注] 600378.SSE\n时间: 2026-07-11 14:52:11"},
    )
    parsed = ares_signal_service.parse_webhook(payload)
    assert parsed.signal_type == "sell"
    assert parsed.stock_code == "600378"


def test_parse_invalid_tag():
    payload = AresSignalWebhook(msgtype="text", text={"content": "无标签 600378.SSE"})
    with pytest.raises(ValueError, match="关注"):
        ares_signal_service.parse_webhook(payload)


def test_build_notification_titles():
    buy = ares_signal_service.parse_webhook(
        AresSignalWebhook(
            msgtype="text",
            text={"content": "[关注] 600378.SSE\n时间: 2026-07-11 10:15:04"},
        )
    )
    title, _, notice_type = ares_signal_service._build_notification(buy)
    assert title == "买点信号 · 600378"
    assert notice_type == "buy_signal"

    sell = ares_signal_service.parse_webhook(
        AresSignalWebhook(
            msgtype="text",
            text={"content": "[取消关注] 000001.SZSE\n时间: 2026-07-11 14:52:11"},
        )
    )
    title2, _, notice_type2 = ares_signal_service._build_notification(sell)
    assert title2 == "卖点信号 · 000001"
    assert notice_type2 == "sell_signal"
