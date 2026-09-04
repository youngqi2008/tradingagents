"""小程序认证 API（仿 akang_lg：wx-login / me / 资料更新 / 头像上传）"""

import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.core.config import settings
from app.routers.mp.deps import get_current_mp_user
from app.services.auth_service import AuthService
from app.services.user_service import user_service
from app.services.wechat_service import wechat_service
from app.services.billing_service import billing_service

router = APIRouter()

AVATAR_DIR = Path(settings.UPLOAD_DIR) / "avatars"
AVATAR_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_AVATAR_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_AVATAR_SIZE = 2 * 1024 * 1024


class MpLoginRequest(BaseModel):
    code: str = Field(..., description="wx.login 获取的 code，开发模式可用 dev:xxx")
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None


class MpProfilePatch(BaseModel):
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None


async def _build_mp_user_payload(user) -> dict:
    """组装登录/资料返回；计费或权益异常时仍返回基础用户信息，避免登录整体 500。"""
    import logging

    from app.models.role import DEFAULT_MP_ROLE, role_display_name

    logger = logging.getLogger("webapi")
    role = getattr(user, "role", None) or DEFAULT_MP_ROLE
    base = {
        "id": str(user.id),
        "nickname": user.nickname,
        "avatar_url": user.avatar_url,
        "balance": float(user.balance or 0),
        "role": role,
        "role_name": role_display_name(role),
        "membership_level_id": user.membership_level_id,
        "membership_level_name": "普通会员",
        "monthly_fee": 0,
        "membership_fee_paid": True,
        "report_free_remaining": 0,
        "report_free_limit": 0,
        "ask_free_remaining": 0,
        "ask_free_limit": 0,
        "report_price": 0,
        "ask_price": 0,
        "can_generate": False,
        "can_ask": False,
        "report_benefit_remaining": 0,
        "ask_benefit_remaining": 0,
        "push_benefit_remaining": 0,
        "benefit_grants": [],
        "free_remaining": 0,
    }
    try:
        quota = await billing_service.get_quota_usage(str(user.id))
        report_check = await billing_service.check_can_generate(str(user.id))
        ask_check = await billing_service.check_can_ask(str(user.id))
        level_name = report_check.get("membership_level_name", "普通会员")
        base.update(
            {
                "membership_level_name": level_name,
                "monthly_fee": quota.get("monthly_fee", 0),
                "membership_fee_paid": quota.get("membership_fee_charged", True),
                "report_free_remaining": quota.get("report_remaining", 0),
                "report_free_limit": quota.get("report_limit", 0),
                "ask_free_remaining": quota.get("ask_remaining", 0),
                "ask_free_limit": quota.get("ask_limit", 0),
                "report_price": report_check.get("report_price", report_check.get("price", 0)),
                "ask_price": ask_check.get("ask_price", ask_check.get("price", 0)),
                "can_generate": report_check.get("can_generate", False),
                "can_ask": ask_check.get("can_use", False),
                "report_benefit_remaining": quota.get("report_benefit_remaining", 0),
                "ask_benefit_remaining": quota.get("ask_benefit_remaining", 0),
                "push_benefit_remaining": quota.get("push_benefit_remaining", 0),
                "benefit_grants": quota.get("benefit_grants") or [],
                "free_remaining": quota.get("report_remaining", 0),
            }
        )
    except Exception as e:
        logger.exception("组装小程序用户额度失败（登录仍放行）: %s", e)
    return base


async def _issue_tokens(username: str) -> dict:
    token = AuthService.create_access_token(
        sub=username,
        expires_minutes=settings.MP_ACCESS_TOKEN_EXPIRE_MINUTES,
        token_type="access",
    )
    refresh_token = AuthService.create_refresh_token(sub=username)
    return {
        "access_token": token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": settings.MP_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post("/auth/login")
@router.post("/auth/wx-login")
async def mp_login(payload: MpLoginRequest):
    """微信小程序登录（首次自动注册）"""
    import logging

    logger = logging.getLogger("webapi")
    try:
        session = await wechat_service.code_to_session(payload.code)
        user = await user_service.get_or_create_mp_user(
            openid=session["openid"],
            unionid=session.get("unionid"),
            nickname=payload.nickname,
            avatar_url=payload.avatar_url,
            session_key=session.get("session_key"),
        )
        tokens = await _issue_tokens(user.username)
        user_payload = await _build_mp_user_payload(user)
        return {
            "success": True,
            "data": {**tokens, "user": user_payload},
            "message": "登录成功",
            **tokens,
            "user": user_payload,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        err_name = type(e).__name__
        err_text = str(e) or err_name
        logger.exception("小程序登录失败: %s", err_text)
        # MySQL / 连接类错误给出可操作提示，避免只看到笼统 500
        lower = err_text.lower()
        if any(
            k in lower
            for k in (
                "mysql",
                "aiomysql",
                "operationalerror",
                "can't connect",
                "connection refused",
                "timed out",
                "access denied",
                "unknown database",
            )
        ) or "OperationalError" in err_name:
            raise HTTPException(
                status_code=503,
                detail=(
                    "登录失败：无法连接 MySQL（用户库）。"
                    f"请检查服务器 .env 中 MYSQL_HOST/PORT/PASSWORD，以及容器能否访问。原始错误: {err_text}"
                ),
            )
        raise HTTPException(status_code=500, detail=f"登录失败: {err_name}: {err_text}")


@router.get("/auth/me")
async def mp_me(user: dict = Depends(get_current_mp_user)):
    """当前登录用户（与 akang_lg /auth/me 对齐）"""
    db_user = await user_service.get_user_by_id(user["id"])
    if not db_user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user_payload = await _build_mp_user_payload(db_user)
    return {"success": True, "data": user_payload, "user": user_payload}


@router.patch("/auth/me")
async def mp_update_me(
    patch: MpProfilePatch,
    user: dict = Depends(get_current_mp_user),
):
    """更新昵称/头像 URL"""
    if patch.nickname is None and patch.avatar_url is None:
        raise HTTPException(status_code=400, detail="无更新内容")
    updated = await user_service.update_mp_profile(
        user["id"],
        nickname=patch.nickname,
        avatar_url=patch.avatar_url,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="用户不存在")
    user_payload = await _build_mp_user_payload(updated)
    return {"success": True, "message": "更新成功", "data": user_payload, "user": user_payload}


@router.post("/auth/me/avatar")
async def mp_upload_avatar(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_mp_user),
):
    """上传头像（仿 akang_lg）"""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_AVATAR_EXT:
        raise HTTPException(status_code=400, detail="仅支持 jpg/jpeg/png/webp/gif")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="空文件")
    if len(data) > MAX_AVATAR_SIZE:
        raise HTTPException(status_code=413, detail="头像超过 2MB 限制")

    name = f"{user['id']}_{uuid.uuid4().hex[:8]}{suffix}"
    abs_path = AVATAR_DIR / name
    abs_path.write_bytes(data)

    avatar_url = f"/uploads/avatars/{name}"
    updated = await user_service.update_mp_profile(user["id"], avatar_url=avatar_url)
    if not updated:
        raise HTTPException(status_code=404, detail="用户不存在")
    user_payload = await _build_mp_user_payload(updated)
    return {
        "success": True,
        "avatar_url": avatar_url,
        "data": user_payload,
        "user": user_payload,
    }
