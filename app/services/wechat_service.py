"""微信服务 - 小程序登录（仿 akang_lg 流程）"""

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


wechat_service = WeChatService()
