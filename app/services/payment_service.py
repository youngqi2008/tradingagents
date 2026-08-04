"""微信支付服务 - MySQL"""

import base64
import json
import secrets
import time
from decimal import Decimal
from typing import Optional

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


class PaymentService:
    JSAPI_URL = "https://api.mch.weixin.qq.com/v3/pay/transactions/jsapi"

    @staticmethod
    def _generate_order_no() -> str:
        return f"R{now_tz().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(4).upper()}"

    def _is_mock_mode(self) -> bool:
        if settings.WECHAT_PAY_MOCK and settings.DEBUG:
            return True
        return not settings.WECHAT_PAY_ENABLED

    async def create_recharge_order(self, user_id: str, openid: str, amount: Decimal) -> dict:
        if amount <= 0:
            raise ValueError("充值金额必须大于 0")

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
                description=f"账户充值 {amount} 元",
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
                "mock": True,
                "message": "开发模式：充值已自动到账",
                "pay_params": None,
            }

        pay_params = await self._create_jsapi_prepay(order_no, openid, amount)
        return {
            "order_no": order_no,
            "amount": float(amount),
            "mock": False,
            "pay_params": pay_params,
        }

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
            "amount": {"total": int(amount * 100), "currency": "CNY"},
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

        private_key = serialization.load_pem_private_key(
            settings.WECHAT_MCH_PRIVATE_KEY.encode("utf-8"),
            password=None,
        )
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

    async def handle_notify(self, headers: dict, body: bytes) -> dict:
        if self._is_mock_mode():
            return {"code": "SUCCESS", "message": "mock"}

        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

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
            remark=f"微信充值 {amount} 元",
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
