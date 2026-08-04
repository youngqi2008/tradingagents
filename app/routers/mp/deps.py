"""小程序 API 依赖"""

from typing import Optional

from fastapi import Depends, HTTPException, Header

from app.routers.auth_db import get_current_user
from app.services.user_service import user_service

try:
    from tradingagents.utils.logging_manager import get_logger
except ImportError:
    import logging
    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)

logger = get_logger("mp_deps")


async def get_current_mp_user(authorization: Optional[str] = Header(default=None)) -> dict:
    """获取当前小程序用户"""
    user = await get_current_user(authorization)
    db_user = await user_service.get_user_by_id(user["id"])
    if not db_user or db_user.user_type != "mp_user":
        raise HTTPException(status_code=403, detail="仅小程序用户可访问")
    return {
        **user,
        "user_type": db_user.user_type,
        "role": getattr(db_user, "role", None) or "normal",
        "openid": db_user.openid,
        "nickname": db_user.nickname,
        "avatar_url": db_user.avatar_url,
        "membership_level_id": db_user.membership_level_id,
        "balance": float(db_user.balance or 0),
    }


async def get_current_risk_officer(user: dict = Depends(get_current_mp_user)) -> dict:
    """仅启用中的风控专员可访问"""
    from app.models.role import ROLE_RISK_OFFICER
    from app.services.role_service import role_service

    if user.get("role") != ROLE_RISK_OFFICER:
        raise HTTPException(status_code=403, detail="仅风控专员可操作")
    if not await role_service.is_valid_role(ROLE_RISK_OFFICER, active_only=True):
        raise HTTPException(status_code=403, detail="风控专员角色已停用")
    return user


async def get_current_admin_user(authorization: Optional[str] = Header(default=None)) -> dict:
    """获取当前运营管理员"""
    user = await get_current_user(authorization)
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
