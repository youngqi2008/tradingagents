"""微信支付服务 - MySQL"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

import httpx
from sqlalchemy import func, select

from app.core.config import settings
from app.core.mysql_db import get_mysql_session, mysql_session, parse_int_id
from app.models.billing import BillingActionType
from app.models.payment import PaymentStatus, PaymentOrderResponse
from app.models.sql.converters import payment_to_response
from app.models.sql.models import PaymentOrderORM
from app.services.billing_service import billing_service
from app.utils.timezone import now_tz

try:
    from tradingagents.utils.logging_manager import get_logger
except ImportError:
    import logging

    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)

logger = get_logger("payment_service")

RECHARGE_AMOUNTS = [Decimal("10"), Decimal("30"), Decimal("50"), Decimal("100"), Decimal("200")]
RECHARGE_MIN = Decimal("1")
RECHARGE_MAX = Decimal("5000")
XPAY_CLIENT_URI = "requestVirtualPayment"
XPAY_QUERY_URI = "/xpay/query_order"
XPAY_PAID_STATUS = {2, 3}  # 已支付 / 已发货


def normalize_recharge_amount(amount: Decimal) -> Decimal:
    value = Decimal(str(amount)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if value < RECHARGE_MIN or value > RECHARGE_MAX:
        raise ValueError(f"充值金额须为 {int(RECHARGE_MIN)}～{int(RECHARGE_MAX)} 的整数元")
    return value


def _hmac_sha256_hex(key: str, message: str) -> str:
    return hmac.new(key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def _json_compact(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class PaymentService:
    JSAPI_URL = "https://api.mch.weixin.qq.com/v3/pay/transactions/jsapi"
    XPAY_QUERY_URL = "https://api.weixin.qq.com/xpay/query_order"

    @staticmethod
    def _generate_order_no() -> str:
        return f"R{now_tz().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(4).upper()}"

    def _is_mock_mode(self) -> bool:
        if settings.WECHAT_PAY_MOCK and settings.DEBUG:
            return True
        return not settings.WECHAT_PAY_ENABLED and not self._xpay_configured()

    def _xpay_configured(self) -> bool:
        offer = (settings.WECHAT_XPAY_OFFER_ID or "").strip()
        return bool(offer and self._xpay_app_key())

    def _xpay_env(self) -> int:
        return 1 if int(settings.WECHAT_XPAY_ENV or 0) == 1 else 0

    def _xpay_app_key(self) -> str:
        if self._xpay_env() == 1:
            return (settings.WECHAT_XPAY_SANDBOX_APP_KEY or settings.WECHAT_XPAY_APP_KEY or "").strip()
        return (settings.WECHAT_XPAY_APP_KEY or "").strip()

    def _coin_ratio(self) -> int:
        ratio = int(settings.WECHAT_XPAY_COIN_RATIO or 1)
        return ratio if ratio > 0 else 1

    def recharge_options(self) -> dict:
        return {
            "mode": "short_series_coin",
            "amounts": [float(a) for a in RECHARGE_AMOUNTS],
            "min_amount": float(RECHARGE_MIN),
            "max_amount": float(RECHARGE_MAX),
            "integer_only": True,
            "coin_ratio": self._coin_ratio(),
            "xpay_enabled": self._xpay_configured(),
        }

    async def create_recharge_order(self, user_id: str, openid: str, amount: Decimal) -> dict:
        amount = normalize_recharge_amount(amount)

        uid = parse_int_id(user_id)
        if not uid:
            raise ValueError("用户不存在")

        order_no = self._generate_order_no()
        now = now_tz()
        async with get_mysql_session() as session:
            row = PaymentOrderORM(
                order_no=order_no,
                user_id=uid,
                openid=openid,
                amount=amount,
                status=PaymentStatus.PENDING.value,
                description=f"代币充值 {int(amount)} 元",
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.flush()

        if self._is_mock_mode():
            await self._complete_order(order_no, wx_transaction_id=f"MOCK_{order_no}")
            return {
                "order_no": order_no,
                "amount": float(amount),
                "buy_quantity": int(amount) * self._coin_ratio(),
                "mock": True,
                "mode": "short_series_coin",
                "message": "开发模式：充值已自动到账",
                "pay_params": None,
            }

        if not self._xpay_configured():
            raise ValueError("未配置小程序虚拟支付，请在公众平台开通并填写 WECHAT_XPAY_OFFER_ID / WECHAT_XPAY_APP_KEY")

        from app.services.user_service import user_service

        session_key = await user_service.get_wx_session_key(user_id)
        if not session_key:
            raise ValueError("登录态已失效，请重新登录后再支付")

        buy_quantity = int(amount) * self._coin_ratio()
        sign_data_obj = {
            "offerId": str(settings.WECHAT_XPAY_OFFER_ID).strip(),
            "buyQuantity": buy_quantity,
            "env": self._xpay_env(),
            "currencyType": "CNY",
            "outTradeNo": order_no,
            "attach": str(uid),
        }
        sign_data = _json_compact(sign_data_obj)
        pay_sig = _hmac_sha256_hex(self._xpay_app_key(), f"{XPAY_CLIENT_URI}&{sign_data}")
        signature = _hmac_sha256_hex(session_key, sign_data)
        return {
            "order_no": order_no,
            "amount": float(amount),
            "buy_quantity": buy_quantity,
            "mock": False,
            "mode": "short_series_coin",
            "pay_params": {
                "mode": "short_series_coin",
                "signData": sign_data,
                "paySig": pay_sig,
                "signature": signature,
            },
        }

    async def confirm_recharge_order(self, order_no: str, user_id: str) -> dict:
        order = await self.get_order(order_no, user_id=user_id)
        if not order:
            raise ValueError("订单不存在")
        if order.status == PaymentStatus.PAID.value:
            return {"order_no": order_no, "status": "paid", "amount": order.amount}
        paid = await self._query_and_complete(order_no, order.user_id)
        return {
            "order_no": order_no,
            "status": "paid" if paid else "pending",
            "amount": order.amount,
        }

    async def _query_and_complete(self, order_no: str, user_id: str) -> bool:
        if not self._xpay_configured():
            return False
        async with get_mysql_session() as session:
            result = await session.execute(
                select(PaymentOrderORM).where(PaymentOrderORM.order_no == order_no)
            )
            row = result.scalar_one_or_none()
            if not row:
                return False
            if row.status == PaymentStatus.PAID.value:
                return True
            openid = row.openid
        data = await self._xpay_query_order(openid, order_no)
        if not data:
            return False
        errcode = data.get("errcode", data.get("errCode"))
        if errcode not in (0, None, "0"):
            logger.info("虚拟支付查单未成功 order=%s data=%s", order_no, data)
            return False
        info = data.get("order") or data.get("Order") or data
        status = info.get("status", info.get("Status"))
        try:
            status_i = int(status)
        except (TypeError, ValueError):
            status_i = -1
        if status_i not in XPAY_PAID_STATUS:
            return False
        wx_id = (
            info.get("wx_order_id")
            or info.get("wxOrderId")
            or info.get("transaction_id")
            or info.get("TransactionId")
        )
        return await self._complete_order(order_no, wx_transaction_id=str(wx_id) if wx_id else None)

    async def _xpay_query_order(self, openid: str, order_no: str) -> Optional[dict]:
        from app.services.wechat_service import wechat_service

        body = {
            "openid": openid,
            "env": self._xpay_env(),
            "order_id": order_no,
        }
        body_str = _json_compact(body)
        pay_sig = _hmac_sha256_hex(self._xpay_app_key(), f"{XPAY_QUERY_URI}&{body_str}")
        try:
            token = await wechat_service.get_client_access_token()
        except ValueError as e:
            logger.error("虚拟支付查单获取 token 失败: %s", e)
            return None
        url = f"{self.XPAY_QUERY_URL}?access_token={token}&pay_sig={pay_sig}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    url,
                    content=body_str.encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                return resp.json()
        except Exception as e:
            logger.error("虚拟支付查单失败: %s", e)
            return None

    def verify_xpay_url(self, signature: str, timestamp: str, nonce: str, echostr: str) -> Optional[str]:
        token = (settings.WECHAT_XPAY_PUSH_TOKEN or "").strip()
        if not token:
            return echostr
        items = sorted([token, timestamp or "", nonce or ""])
        digest = hashlib.sha1("".join(items).encode("utf-8")).hexdigest()
        if digest != (signature or "").lower():
            return None
        return echostr

    async def handle_xpay_notify(self, headers: dict, body: bytes) -> dict:
        try:
            payload = self._parse_xpay_payload(body)
        except Exception as e:
            logger.error("虚拟支付推送解析失败: %s", e)
            return {"ErrCode": -1, "ErrMsg": "parse error"}

        event = str(payload.get("Event") or payload.get("event") or "")
        order_no = str(payload.get("OutTradeNo") or payload.get("outTradeNo") or payload.get("MchOrderId") or "")
        if event in ("xpay_coin_pay_notify", "xpay_goods_deliver_notify") and order_no:
            wx_info = payload.get("WeChatPayInfo") or payload.get("weChatPayInfo") or {}
            wx_id = wx_info.get("TransactionId") or wx_info.get("transactionId")
            try:
                await self._complete_order(order_no, wx_transaction_id=str(wx_id) if wx_id else None)
            except Exception as e:
                logger.error("虚拟支付入账失败 order=%s: %s", order_no, e)
                return {"ErrCode": -1, "ErrMsg": "deliver fail"}
        elif event == "xpay_refund_notify":
            logger.warning("收到虚拟支付退款推送: %s", payload)
        return {"ErrCode": 0, "ErrMsg": "success"}

    def _parse_xpay_payload(self, body: bytes) -> dict:
        raw = (body or b"").decode("utf-8", errors="ignore").strip()
        if not raw:
            return {}
        data: dict[str, Any]
        if raw.startswith("<"):
            data = self._xml_to_dict(raw)
        else:
            data = json.loads(raw)
        encrypt = data.get("Encrypt") or data.get("encrypt")
        if encrypt:
            decrypted = self._decrypt_xpay_message(str(encrypt))
            if decrypted.startswith("{"):
                return json.loads(decrypted)
            return self._xml_to_dict(decrypted)
        return data

    def _decrypt_xpay_message(self, encrypt: str) -> str:
        aes_key_b64 = (settings.WECHAT_XPAY_ENCODING_AES_KEY or "").strip()
        if not aes_key_b64:
            raise ValueError("未配置 WECHAT_XPAY_ENCODING_AES_KEY")
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        key = base64.b64decode(aes_key_b64 + "=")
        cipher = Cipher(algorithms.AES(key), modes.CBC(key[:16]))
        decryptor = cipher.decryptor()
        plain = decryptor.update(base64.b64decode(encrypt)) + decryptor.finalize()
        pad = plain[-1]
        plain = plain[:-pad] if 1 <= pad <= 32 else plain
        content = plain[16:]
        msg_len = int.from_bytes(content[:4], "big")
        return content[4:4 + msg_len].decode("utf-8")

    @staticmethod
    def _xml_to_dict(xml_text: str) -> dict:
        import re

        pairs = re.findall(r"<(\w+)><!\[CDATA\[(.*?)\]\]></\1>|<(\w+)>([^<]*)</\3>", xml_text)
        result = {}
        for a, b, c, d in pairs:
            if a:
                result[a] = b
            elif c:
                result[c] = d
        return result

    async def _create_jsapi_prepay(self, order_no: str, openid: str, amount: Decimal) -> dict:
        if not all([
            settings.WECHAT_MINI_APP_ID,
            settings.WECHAT_MCH_ID,
            settings.WECHAT_API_V3_KEY,
            settings.WECHAT_MCH_PRIVATE_KEY,
        ]):
            raise ValueError("微信支付未完整配置")

        body = {
            "appid": settings.WECHAT_MINI_APP_ID,
            "mchid": settings.WECHAT_MCH_ID,
            "description": "Ares智能研报-账户充值",
            "out_trade_no": order_no,
            "notify_url": settings.WECHAT_PAY_NOTIFY_URL,
            "amount": {"total": int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)), "currency": "CNY"},
            "payer": {"openid": openid},
        }
        body_str = json.dumps(body, ensure_ascii=False)
        authorization = self._build_authorization("POST", "/v3/pay/transactions/jsapi", body_str)

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                self.JSAPI_URL,
                content=body_str.encode("utf-8"),
                headers={
                    "Authorization": authorization,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            data = resp.json()

        if resp.status_code != 200:
            logger.error(f"微信下单失败: {data}")
            raise ValueError(data.get("message", "微信下单失败"))

        prepay_id = data.get("prepay_id")
        async with get_mysql_session() as session:
            result = await session.execute(
                select(PaymentOrderORM).where(PaymentOrderORM.order_no == order_no)
            )
            order = result.scalar_one_or_none()
            if order:
                order.wx_prepay_id = prepay_id
                order.updated_at = now_tz()
        return self._build_mini_program_pay_params(prepay_id)

    def _build_mini_program_pay_params(self, prepay_id: str) -> dict:
        timestamp = str(int(time.time()))
        nonce_str = secrets.token_hex(16)
        package = f"prepay_id={prepay_id}"
        message = f"{settings.WECHAT_MINI_APP_ID}\n{timestamp}\n{nonce_str}\n{package}\n"
        signature = self._sign_message(message)
        return {
            "timeStamp": timestamp,
            "nonceStr": nonce_str,
            "package": package,
            "signType": "RSA",
            "paySign": signature,
        }

    def _sign_message(self, message: str) -> str:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        pem = (settings.WECHAT_MCH_PRIVATE_KEY or "").encode("utf-8")
        try:
            private_key = serialization.load_pem_private_key(pem, password=None)
        except ValueError as e:
            raise ValueError(
                "商户私钥 PEM 无法解析。请确认 WECHAT_MCH_PRIVATE_KEY 为 apiclient_key.pem 全文，"
                "换行可用 \\n，且包含 BEGIN/END PRIVATE KEY"
            ) from e
        signature = private_key.sign(
            message.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("utf-8")

    def _build_authorization(self, method: str, url_path: str, body: str) -> str:
        timestamp = str(int(time.time()))
        nonce_str = secrets.token_hex(16)
        message = f"{method}\n{url_path}\n{timestamp}\n{nonce_str}\n{body}\n"
        signature = self._sign_message(message)
        return (
            f'WECHATPAY2-SHA256-RSA2048 mchid="{settings.WECHAT_MCH_ID}",'
            f'nonce_str="{nonce_str}",signature="{signature}",'
            f'timestamp="{timestamp}",serial_no="{settings.WECHAT_MCH_SERIAL_NO}"'
        )

    def _verify_wechat_notify(self, headers: dict, body: bytes) -> bool:
        """用微信支付公钥校验回调签名；未配置公钥时跳过验签。"""
        pub_pem = settings.WECHAT_PAY_PUBLIC_KEY
        if not pub_pem:
            logger.warning("未配置 WECHAT_PAY_PUBLIC_KEY，跳过支付回调验签")
            return True

        header_map = {str(k).lower(): v for k, v in headers.items()}
        timestamp = header_map.get("wechatpay-timestamp", "")
        nonce = header_map.get("wechatpay-nonce", "")
        signature = header_map.get("wechatpay-signature", "")
        if not all([timestamp, nonce, signature]):
            logger.error("支付回调缺少验签头")
            return False

        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding

            public_key = serialization.load_pem_public_key(pub_pem.encode("utf-8"))
            message = f"{timestamp}\n{nonce}\n{body.decode('utf-8')}\n"
            public_key.verify(
                base64.b64decode(signature),
                message.encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            return True
        except Exception as e:
            logger.error(f"支付回调验签失败: {e}")
            return False

    async def handle_notify(self, headers: dict, body: bytes) -> dict:
        if self._is_mock_mode():
            return {"code": "SUCCESS", "message": "mock"}

        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            if not self._verify_wechat_notify(headers, body):
                return {"code": "FAIL", "message": "invalid signature"}

            data = json.loads(body)
            resource = data.get("resource", {})
            nonce = resource.get("nonce")
            ciphertext = resource.get("associated_data", "")
            encrypted = resource.get("ciphertext")
            if not all([nonce, encrypted]):
                return {"code": "FAIL", "message": "invalid resource"}

            key = settings.WECHAT_API_V3_KEY.encode("utf-8")
            aesgcm = AESGCM(key)
            decrypted = aesgcm.decrypt(
                nonce.encode("utf-8"),
                base64.b64decode(encrypted),
                ciphertext.encode("utf-8") if ciphertext else None,
            )
            pay_data = json.loads(decrypted.decode("utf-8"))
            if pay_data.get("trade_state") == "SUCCESS":
                await self._complete_order(
                    pay_data["out_trade_no"],
                    wx_transaction_id=pay_data.get("transaction_id"),
                )
            return {"code": "SUCCESS", "message": "成功"}
        except Exception as e:
            logger.error(f"支付回调处理失败: {e}", exc_info=True)
            return {"code": "FAIL", "message": str(e)}

    async def _complete_order(self, order_no: str, wx_transaction_id: Optional[str] = None) -> bool:
        async with mysql_session() as session:
            async with session.begin():
                result = await session.execute(
                    select(PaymentOrderORM)
                    .where(
                        PaymentOrderORM.order_no == order_no,
                        PaymentOrderORM.status == PaymentStatus.PENDING.value,
                    )
                    .with_for_update()
                )
                order = result.scalar_one_or_none()
                if not order:
                    return False
                order.status = PaymentStatus.PAID.value
                order.wx_transaction_id = wx_transaction_id
                order.paid_at = now_tz()
                order.updated_at = now_tz()
                amount = Decimal(str(order.amount))
                user_id = str(order.user_id)

        await billing_service.add_balance(
            user_id=user_id,
            amount=amount,
            action_type=BillingActionType.RECHARGE,
            order_no=order_no,
            remark=f"虚拟支付充值 {amount} 元",
        )
        await billing_service.ensure_monthly_fee(user_id)
        logger.info(f"✅ 充值成功: {order_no}, 金额 {amount}")
        return True

    async def get_order(self, order_no: str, user_id: Optional[str] = None) -> Optional[PaymentOrderResponse]:
        async with get_mysql_session() as session:
            stmt = select(PaymentOrderORM).where(PaymentOrderORM.order_no == order_no)
            if user_id:
                uid = parse_int_id(user_id)
                if uid:
                    stmt = stmt.where(PaymentOrderORM.user_id == uid)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            return payment_to_response(row) if row else None

    async def list_orders(
        self,
        user_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list:
        async with get_mysql_session() as session:
            stmt = select(PaymentOrderORM).order_by(PaymentOrderORM.created_at.desc())
            if user_id:
                uid = parse_int_id(user_id)
                if uid:
                    stmt = stmt.where(PaymentOrderORM.user_id == uid)
            stmt = stmt.offset(skip).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [payment_to_response(r) for r in rows]

    async def count_orders(self, user_id: Optional[str] = None) -> int:
        async with get_mysql_session() as session:
            stmt = select(func.count(PaymentOrderORM.id))
            if user_id:
                uid = parse_int_id(user_id)
                if uid:
                    stmt = stmt.where(PaymentOrderORM.user_id == uid)
            return (await session.execute(stmt)).scalar() or 0


payment_service = PaymentService()
