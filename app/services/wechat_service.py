"""微信服务 - 小程序登录（仿 akang_lg 流程）"""

import time
from datetime import datetime
from typing import Iterable, Optional

import httpx

from app.core.config import settings

try:
    from tradingagents.utils.logging_manager import get_logger
except ImportError:
    import logging

    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)

logger = get_logger("wechat_service")


class WeChatService:
    CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"
    TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
    SUBSCRIBE_SEND_URL = "https://api.weixin.qq.com/cgi-bin/message/subscribe/send"

    def __init__(self):
        self._client_token = ""
        self._client_token_expire_at = 0.0

    def _use_dev_login(self, code: str) -> bool:
        """
        仅当显式开启 WECHAT_ALLOW_DEV_LOGIN 时允许 mock/dev 登录。
        生产环境（DEBUG=false）一律禁止。
        """
        if settings.is_production:
            return False
        if not settings.WECHAT_ALLOW_DEV_LOGIN:
            return False
        if (code or "").startswith("dev:"):
            return True
        if not settings.WECHAT_MINI_APP_ID or not settings.WECHAT_MINI_APP_SECRET:
            return True
        return False

    def _dev_session(self, code: str) -> dict:
        seed = (code or "anonymous").strip()
        if seed.startswith("dev:"):
            seed = seed[4:] or "anonymous"
        openid = f"dev_{seed[:24]}"
        logger.warning(f"⚠️ 开发模式微信登录: openid={openid}")
        return {
            "openid": openid,
            "session_key": "dev_session_key",
            "unionid": None,
        }

    async def code_to_session(self, code: str) -> dict:
        if self._use_dev_login(code):
            return self._dev_session(code)

        if not settings.WECHAT_MINI_APP_ID or not settings.WECHAT_MINI_APP_SECRET:
            raise ValueError("微信小程序未配置，请设置 WECHAT_MINI_APP_ID 和 WECHAT_MINI_APP_SECRET")

        params = {
            "appid": settings.WECHAT_MINI_APP_ID,
            "secret": settings.WECHAT_MINI_APP_SECRET,
            "js_code": code,
            "grant_type": "authorization_code",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(self.CODE2SESSION_URL, params=params)
                data = resp.json()
        except httpx.TimeoutException:
            raise ValueError("微信服务响应超时，请稍后重试")
        except httpx.HTTPError as e:
            raise ValueError(f"微信服务请求失败: {type(e).__name__}")
        except ValueError:
            raise ValueError("微信登录响应解析失败")

        errcode = data.get("errcode", 0)
        if errcode != 0:
            logger.error(f"微信登录失败: {data}")
            raise ValueError(data.get("errmsg", "微信登录失败"))

        openid = data.get("openid")
        if not openid:
            raise ValueError("微信登录失败: 未返回 openid")

        return {
            "openid": openid,
            "session_key": data.get("session_key"),
            "unionid": data.get("unionid"),
        }

    def subscribe_config(self) -> dict:
        tmpl = (settings.WECHAT_SUBSCRIBE_TEMPLATE_SIGNAL or "").strip()
        return {
            "enabled": bool(tmpl and settings.WECHAT_MINI_APP_ID),
            "template_ids": [tmpl] if tmpl else [],
            "page": settings.WECHAT_SUBSCRIBE_PAGE or "pages/signals/signals",
        }

    async def get_client_access_token(self) -> str:
        now = time.time()
        if self._client_token and now < self._client_token_expire_at - 60:
            return self._client_token
        if not settings.WECHAT_MINI_APP_ID or not settings.WECHAT_MINI_APP_SECRET:
            raise ValueError("微信小程序未配置")
        params = {
            "grant_type": "client_credential",
            "appid": settings.WECHAT_MINI_APP_ID,
            "secret": settings.WECHAT_MINI_APP_SECRET,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(self.TOKEN_URL, params=params)
            data = resp.json()
        token = data.get("access_token")
        if not token:
            logger.error("获取微信接口 token 失败: %s", data)
            raise ValueError(data.get("errmsg") or "获取微信接口凭证失败")
        self._client_token = token
        self._client_token_expire_at = now + int(data.get("expires_in") or 7200)
        return token

    def _clip(self, text: str, limit: int) -> str:
        s = (text or "").replace("\n", " ").strip()
        if len(s) <= limit:
            return s
        return s[: max(0, limit - 1)] + "…"

    def _build_subscribe_data(self, title: str, content: str, notice_type: str) -> dict:
        tip = "关注" if notice_type == "buy_signal" else ("提醒" if notice_type == "sell_signal" else "通知")
        now = datetime.now().strftime("%Y年%m月%d日 %H:%M")
        payload = {
            settings.WECHAT_SUBSCRIBE_FIELD_TITLE: {"value": self._clip(title, 20)},
            settings.WECHAT_SUBSCRIBE_FIELD_TIME: {"value": now},
            settings.WECHAT_SUBSCRIBE_FIELD_TIP: {"value": self._clip(content or tip, 20)},
        }
        return {k: v for k, v in payload.items() if k}

    async def send_subscribe_message(
        self,
        openid: str,
        *,
        title: str,
        content: str,
        notice_type: str,
        page: Optional[str] = None,
    ) -> bool:
        tmpl = (settings.WECHAT_SUBSCRIBE_TEMPLATE_SIGNAL or "").strip()
        if not tmpl or not openid or str(openid).startswith("dev_"):
            return False
        token = await self.get_client_access_token()
        body = {
            "touser": openid,
            "template_id": tmpl,
            "page": page or settings.WECHAT_SUBSCRIBE_PAGE or "pages/signals/signals",
            "miniprogram_state": settings.WECHAT_MINI_PROGRAM_STATE or "formal",
            "lang": "zh_CN",
            "data": self._build_subscribe_data(title, content, notice_type),
        }
        url = f"{self.SUBSCRIBE_SEND_URL}?access_token={token}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=body)
            data = resp.json()
        errcode = data.get("errcode", 0)
        if errcode == 0:
            return True
        # 43101 用户未订阅 / 拒绝；不视为系统故障
        if errcode in (43101, 43108, 47003):
            logger.info("订阅消息未送达 openid=%s err=%s %s", openid[-8:], errcode, data.get("errmsg"))
            return False
        logger.warning("订阅消息发送失败 openid=%s data=%s", openid[-8:], data)
        return False

    async def notify_signal_subscribers(
        self,
        openids: Iterable[str],
        title: str,
        content: str,
        notice_type: str,
    ) -> int:
        tmpl = (settings.WECHAT_SUBSCRIBE_TEMPLATE_SIGNAL or "").strip()
        if not tmpl:
            logger.info("未配置 WECHAT_SUBSCRIBE_TEMPLATE_SIGNAL，跳过微信服务通知")
            return 0
        sent = 0
        seen = set()
        for openid in openids or []:
            oid = (openid or "").strip()
            if not oid or oid in seen:
                continue
            seen.add(oid)
            try:
                ok = await self.send_subscribe_message(
                    oid, title=title, content=content, notice_type=notice_type
                )
                if ok:
                    sent += 1
            except Exception:
                logger.exception("订阅消息发送异常 openid=%s", oid[-8:])
        logger.info("关注信号微信提醒已发送 sent=%s / %s type=%s", sent, len(seen), notice_type)
        return sent


wechat_service = WeChatService()
