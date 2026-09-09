"""微信服务 - 小程序登录（仿 akang_lg 流程）"""

import asyncio
import re
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
            "page": settings.WECHAT_SUBSCRIBE_PAGE or "pages/signal-open/signal-open",
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
        return s[:limit]

    def _sanitize_thing(self, text: str, limit: int = 20) -> str:
        """thing 字段仅允许汉字/数字/字母及 -+*/._,:【】，超长直接截断，不能用省略号。"""
        s = (text or "").replace("\n", " ").replace("·", " ").replace("…", "")
        s = (
            s.replace("关注信号", "服务动态")
            .replace("不关注信号", "服务更新")
            .replace("股票代码", "编号")
            .replace("股票", "项目")
            .replace("复盘", "摘要")
        )
        s = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9\-\+\*/\._,:\s【】]", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        if not s:
            s = "服务动态"
        return self._clip(s, limit)

    def _format_subscribe_time(self) -> str:
        now = datetime.now()
        return f"{now.year}年{now.month}月{now.day}日 {now.hour:02d}:{now.minute:02d}"

    def _build_subscribe_data(self, title: str, content: str, notice_type: str) -> dict:
        label = "服务更新" if notice_type == "sell_signal" else "服务动态"
        safe_title = self._sanitize_thing(title or label)
        payload = {
            settings.WECHAT_SUBSCRIBE_FIELD_TITLE: {"value": safe_title},
            settings.WECHAT_SUBSCRIBE_FIELD_TIME: {"value": self._format_subscribe_time()},
            settings.WECHAT_SUBSCRIBE_FIELD_TIP: {"value": "点击查看详情"},
        }
        return {k: v for k, v in payload.items() if k}

    def _subscribe_jump_page(self, notice_id: Optional[str], page: Optional[str] = None) -> str:
        base = (page or settings.WECHAT_SUBSCRIBE_PAGE or "pages/signal-open/signal-open").split("?")[0]
        nid = str(notice_id or "").strip()
        return f"{base}?id={nid}" if nid else base

    async def send_subscribe_message(
        self,
        openid: str,
        *,
        title: str,
        content: str,
        notice_type: str,
        page: Optional[str] = None,
        notice_id: Optional[str] = None,
    ) -> bool:
        tmpl = (settings.WECHAT_SUBSCRIBE_TEMPLATE_SIGNAL or "").strip()
        if not tmpl or not openid or str(openid).startswith("dev_"):
            return False
        token = await self.get_client_access_token()
        jump = self._subscribe_jump_page(notice_id, page)
        state = (settings.WECHAT_MINI_PROGRAM_STATE or "formal").strip() or "formal"
        body = {
            "touser": openid,
            "template_id": tmpl,
            "page": jump,
            "miniprogram_state": state,
            "lang": "zh_CN",
            "data": self._build_subscribe_data(title, content, notice_type),
        }
        url = f"{self.SUBSCRIBE_SEND_URL}?access_token={token}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=body)
            data = resp.json()
        errcode = data.get("errcode", 0)
        if errcode == 47003:
            logger.warning(
                "订阅消息字段不合规，改用安全文案重试 openid=%s err=%s payload=%s",
                openid[-8:],
                data,
                body.get("data"),
            )
            body["data"] = self._build_subscribe_data("服务动态", "点击查看详情", notice_type)
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=body)
                data = resp.json()
            errcode = data.get("errcode", 0)
        if errcode == 0:
            logger.info(
                "订阅消息已送达 openid=%s notice=%s page=%s state=%s",
                openid[-8:],
                notice_id or "",
                jump,
                state,
            )
            return True
        # 43101 用户拒绝或额度用尽；43108 用户关闭了服务通知
        if errcode in (43101, 43108):
            logger.info(
                "订阅消息未送达(无额度或已关闭) openid=%s err=%s %s state=%s",
                openid[-8:],
                errcode,
                data.get("errmsg"),
                state,
            )
            return False
        logger.warning("订阅消息发送失败 openid=%s data=%s state=%s", openid[-8:], data, state)
        return False

    async def notify_signal_subscribers(
        self,
        openids: Iterable[str],
        title: str,
        content: str,
        notice_type: str,
        notice_id: Optional[str] = None,
    ) -> int:
        tmpl = (settings.WECHAT_SUBSCRIBE_TEMPLATE_SIGNAL or "").strip()
        if not tmpl:
            logger.info("未配置 WECHAT_SUBSCRIBE_TEMPLATE_SIGNAL，跳过微信服务通知")
            return 0
        seen = []
        dup = set()
        for openid in openids or []:
            oid = (openid or "").strip()
            if not oid or oid in dup:
                continue
            dup.add(oid)
            seen.append(oid)
        sent = 0
        batch_size = 8
        for i in range(0, len(seen), batch_size):
            chunk = seen[i : i + batch_size]
            results = await asyncio.gather(
                *[
                    self.send_subscribe_message(
                        oid,
                        title=title,
                        content=content,
                        notice_type=notice_type,
                        notice_id=notice_id,
                    )
                    for oid in chunk
                ],
                return_exceptions=True,
            )
            for oid, result in zip(chunk, results):
                if result is True:
                    sent += 1
                elif isinstance(result, Exception):
                    logger.error("订阅消息发送异常 openid=%s", oid[-8:], exc_info=result)
        logger.info(
            "关注信号微信提醒已发送 sent=%s / %s type=%s notice=%s",
            sent,
            len(seen),
            notice_type,
            notice_id or "",
        )
        return sent


wechat_service = WeChatService()
