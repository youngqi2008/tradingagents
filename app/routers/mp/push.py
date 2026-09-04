"""小程序订阅消息配置"""

from fastapi import APIRouter

from app.services.wechat_service import wechat_service

router = APIRouter()


@router.get("/push/subscribe-config")
async def mp_subscribe_config():
    """小程序端拉取订阅消息模板，用于 wx.requestSubscribeMessage。"""
    cfg = wechat_service.subscribe_config()
    return {"success": True, "data": cfg}
