"""外部买卖点信号 Webhook（公网推送 → 小程序站内信）"""

import logging
import secrets
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request

from app.core.config import settings
from app.models.ares_signal import AresSignalWebhook
from app.services.ares_signal_service import ares_signal_service

router = APIRouter(prefix="/api/ares", tags=["ares-signal"])
logger = logging.getLogger("webapi.ares_signal")


def _verify_signal_token(authorization: Optional[str] = None, x_ares_signal_token: Optional[str] = None) -> None:
    """强制校验 ARES_SIGNAL_TOKEN；未配置或令牌错误一律拒绝。"""
    expected = (getattr(settings, "ARES_SIGNAL_TOKEN", None) or "").strip()
    if not expected:
        logger.error("ARES_SIGNAL_TOKEN 未配置，拒绝信号推送")
        raise HTTPException(
            status_code=503,
            detail="信号推送未启用：请配置 ARES_SIGNAL_TOKEN",
        )

    token = (x_ares_signal_token or "").strip()
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()

    if not token or not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="无效的信号推送令牌")


@router.post("/signal")
async def receive_ares_signal(
    body: AresSignalWebhook,
    request: Request,
    authorization: Optional[str] = Header(None),
    x_ares_signal_token: Optional[str] = Header(None, alias="X-Ares-Signal-Token"),
):
    """
    接收外部买卖点信号，转为小程序全员站内通知。

    请求体示例（买点）::

        {
          "msgtype": "text",
          "text": {
            "content": "[关注] 600378.SSE\\n时间: 2026-07-11 10:15:04"
          }
        }
    """
    _verify_signal_token(authorization, x_ares_signal_token)

    if body.msgtype != "text":
        raise HTTPException(status_code=400, detail="msgtype 仅支持 text")

    client_ip = request.client.host if request.client else "unknown"
    logger.info("收到外部信号推送 ip=%s", client_ip)

    try:
        notification = await ares_signal_service.push_to_miniprogram(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("信号推送失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"信号推送失败: {e}")

    return {
        "success": True,
        "message": "信号已推送",
        "data": {
            "notification_id": notification.id,
            "title": notification.title,
            "notice_type": notification.notice_type,
            "recipient_count": notification.recipient_count,
        },
    }
