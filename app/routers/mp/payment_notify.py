"""支付回调：虚拟支付消息推送 + 历史 JSAPI 回调"""

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from app.services.payment_service import payment_service

router = APIRouter(prefix="/api/mp/payment", tags=["miniprogram-payment"])


@router.post("/notify")
async def wechat_pay_notify(request: Request):
    """历史微信支付 JSAPI 回调（兼容旧订单）"""
    body = await request.body()
    headers = dict(request.headers)
    result = await payment_service.handle_notify(headers, body)
    return result


@router.get("/xpay-notify")
async def xpay_notify_verify(
    signature: str = Query(default=""),
    timestamp: str = Query(default=""),
    nonce: str = Query(default=""),
    echostr: str = Query(default=""),
):
    """公众平台配置消息推送 URL 时的 GET 校验。"""
    echoed = payment_service.verify_xpay_url(signature, timestamp, nonce, echostr)
    if echoed is None:
        return PlainTextResponse("invalid", status_code=403)
    return PlainTextResponse(echoed)


@router.post("/xpay-notify")
async def xpay_notify(request: Request):
    """虚拟支付发货/代币支付推送。响应格式必须为 ErrCode，否则微信会重试。"""
    body = await request.body()
    headers = dict(request.headers)
    result = await payment_service.handle_xpay_notify(headers, body)
    return JSONResponse(result)
