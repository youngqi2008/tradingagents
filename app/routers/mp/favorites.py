"""小程序自选股 API"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.routers.mp.deps import get_current_mp_user
from app.services.favorites_service import favorites_service

router = APIRouter()


def _mp_key(user: dict) -> str:
    return favorites_service.mp_user_key(user["id"])


class MpFavoriteAdd(BaseModel):
    stock_code: str = Field(..., min_length=1, max_length=16)
    stock_name: str = Field("", max_length=64)
    market: str = Field("A股", max_length=16)
    notes: str = ""


@router.get("/favorites")
async def list_my_favorites(user: dict = Depends(get_current_mp_user)):
    items = await favorites_service.get_user_favorites(_mp_key(user))
    return {"success": True, "data": {"favorites": items, "total": len(items)}}


@router.get("/favorites/check/{stock_code}")
async def check_favorite(stock_code: str, user: dict = Depends(get_current_mp_user)):
    ok = await favorites_service.is_favorite(_mp_key(user), stock_code)
    return {"success": True, "data": {"is_favorite": ok}}


@router.post("/favorites")
async def add_favorite(payload: MpFavoriteAdd, user: dict = Depends(get_current_mp_user)):
    code = payload.stock_code.strip().upper()
    # 统一 A 股 6 位
    if code.isdigit():
        code = code.zfill(6)
    key = _mp_key(user)
    if await favorites_service.is_favorite(key, code):
        raise HTTPException(status_code=400, detail="该股票已在自选中")
    name = (payload.stock_name or "").strip() or code
    await favorites_service.add_favorite(
        key,
        stock_code=code,
        stock_name=name,
        market=payload.market or "A股",
        notes=payload.notes or "",
    )
    items = await favorites_service.get_user_favorites(key)
    return {"success": True, "message": "已加入自选", "data": {"favorites": items}}


@router.delete("/favorites/{stock_code}")
async def remove_favorite(stock_code: str, user: dict = Depends(get_current_mp_user)):
    code = stock_code.strip().upper()
    if code.isdigit():
        code = code.zfill(6)
    ok = await favorites_service.remove_favorite(_mp_key(user), code)
    if not ok:
        raise HTTPException(status_code=404, detail="自选中不存在该股票")
    return {"success": True, "message": "已取消自选"}
