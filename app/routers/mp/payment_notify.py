"""微信支付回调"""

from fastapi import APIRouter, Request

from app.services.payment_service import payment_service

router = APIRouter(prefix="/api/mp/payment", tags=["miniprogram-payment"])


@router.post("/notify")
async def wechat_pay_notify(request: Request):
    body = await request.body()
    headers = dict(request.headers)
    result = await payment_service.handle_notify(headers, body)
    return result
