"""小程序问股 API"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.models.mp_chat import ChatAskRequest, ChatSessionCreate
from app.routers.mp.deps import get_current_mp_user
from app.services.billing_service import billing_service, InsufficientBalanceError
from app.services.mp_chat_service import mp_chat_service
from app.services.stock_ask_agent_service import stock_ask_agent_service
from app.services.chat_suggestion_service import chat_suggestion_service

router = APIRouter()
logger = logging.getLogger("webapi")

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class CreateSessionBody(ChatSessionCreate):
    pass


@router.get("/chat/strategies")
async def mp_list_strategies(user: dict = Depends(get_current_mp_user)):
    strategies = stock_ask_agent_service.list_strategies()
    return {
        "success": True,
        "data": {
            "strategies": [
                {"id": s["id"], "name": s["name"], "description": s.get("description", "")}
                for s in strategies
            ]
        },
    }


@router.get("/chat/sessions")
async def mp_list_sessions(user: dict = Depends(get_current_mp_user)):
    sessions = await mp_chat_service.list_user_sessions(user["id"])
    return {"success": True, "data": {"sessions": sessions}}


@router.post("/chat/sessions")
async def mp_create_session(
    body: CreateSessionBody,
    user: dict = Depends(get_current_mp_user),
):
    session = await mp_chat_service.create_session(
        user["id"],
        title=body.title,
        stock_code=body.stock_code,
        strategy_id=body.strategy_id,
    )
    return {"success": True, "data": session, "message": "会话已创建"}


@router.get("/chat/sessions/{session_id}/messages")
async def mp_list_messages(session_id: str, user: dict = Depends(get_current_mp_user)):
    chat_session = await mp_chat_service.get_session_for_user(user["id"], session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = await mp_chat_service.list_messages(session_id)
    return {"success": True, "data": {"messages": messages}}


@router.delete("/chat/sessions/{session_id}")
async def mp_delete_session(session_id: str, user: dict = Depends(get_current_mp_user)):
    ok = await mp_chat_service.delete_session(user["id"], session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"success": True, "message": "已删除"}


@router.post("/chat/sessions/{session_id}/ask")
async def mp_ask_in_session(
    session_id: str,
    body: ChatAskRequest,
    user: dict = Depends(get_current_mp_user),
):
    """问股（同步返回，绑定用户并扣费）"""
    chat_session = await mp_chat_service.get_session_for_user(user["id"], session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if chat_session.status == "disabled":
        raise HTTPException(status_code=403, detail="该问股会话已被禁用")

    check = await billing_service.check_can_ask(user["id"])
    if not check.get("can_use"):
        raise HTTPException(
            status_code=402,
            detail={
                "message": check.get("reason", "余额不足，无法问股"),
                "required": check.get("ask_price", check.get("price", 0)),
                "balance": check.get("balance", 0),
            },
        )

    stock_code = chat_session.stock_code or stock_ask_agent_service.extract_stock_code(body.message)
    try:
        user_msg, reply_msg = await mp_chat_service.ask_in_session(
            user["id"],
            session_id,
            body.message,
            strategy_id=body.strategy_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("问股处理失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"问股失败: {e}")

    charge = None
    follow_up_suggestions: list[str] = []
    if reply_msg.get("status") == "completed":
        follow_up_suggestions = chat_suggestion_service.generate(
            stock_code=stock_code,
            user_message=body.message,
            assistant_reply=reply_msg.get("content") or "",
            strategy_id=body.strategy_id or chat_session.strategy_id,
        )
        try:
            charge = await billing_service.charge_for_ask(
                user_id=user["id"],
                stock_code=stock_code,
                session_id=session_id,
            )
        except InsufficientBalanceError as e:
            raise HTTPException(
                status_code=402,
                detail={
                    "message": str(e),
                    "required": float(e.required),
                    "balance": float(e.balance),
                },
            )

    return {
        "success": True,
        "data": {
            "session_id": session_id,
            "message": user_msg,
            "reply": reply_msg,
            "follow_up_suggestions": follow_up_suggestions,
            "charge": {
                "is_free": charge.is_free,
                "amount": float(charge.amount),
                "balance_after": float(charge.balance_after),
                "message": charge.message,
            } if charge else None,
        },
        "message": "问股完成",
    }


@router.post("/chat/sessions/{session_id}/ask/stream")
async def mp_ask_in_session_stream(
    session_id: str,
    body: ChatAskRequest,
    user: dict = Depends(get_current_mp_user),
):
    """问股 SSE 流式接口：推送分析进度，避免长连接超时。"""
    chat_session = await mp_chat_service.get_session_for_user(user["id"], session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if chat_session.status == "disabled":
        raise HTTPException(status_code=403, detail="该问股会话已被禁用")

    check = await billing_service.check_can_ask(user["id"])
    if not check.get("can_use"):
        raise HTTPException(
            status_code=402,
            detail={
                "message": check.get("reason", "余额不足，无法问股"),
                "required": check.get("ask_price", check.get("price", 0)),
                "balance": check.get("balance", 0),
            },
        )

    async def event_generator():
        yield _format_sse("connected", {"session_id": session_id, "message": "已连接问股流"})
        try:
            async for item in mp_chat_service.stream_ask_in_session(
                user["id"],
                session_id,
                body.message,
                strategy_id=body.strategy_id,
            ):
                event = item.get("event", "message")
                data = item.get("data") or {}

                if event == "assistant_done":
                    reply_msg = data.get("reply") or {}
                    stock_code = data.get("stock_code") or chat_session.stock_code
                    follow_up_suggestions: list[str] = []
                    charge_payload = None

                    if reply_msg.get("status") == "completed":
                        follow_up_suggestions = chat_suggestion_service.generate(
                            stock_code=stock_code,
                            user_message=body.message,
                            assistant_reply=reply_msg.get("content") or "",
                            strategy_id=body.strategy_id or chat_session.strategy_id,
                        )
                        try:
                            charge = await billing_service.charge_for_ask(
                                user_id=user["id"],
                                stock_code=stock_code,
                                session_id=session_id,
                            )
                            charge_payload = {
                                "is_free": charge.is_free,
                                "amount": float(charge.amount),
                                "balance_after": float(charge.balance_after),
                                "message": charge.message,
                            }
                        except InsufficientBalanceError as e:
                            yield _format_sse(
                                "error",
                                {
                                    "code": 402,
                                    "message": str(e),
                                    "required": float(e.required),
                                    "balance": float(e.balance),
                                },
                            )
                            return

                    done_data = {
                        "session_id": session_id,
                        "message": data.get("message"),
                        "reply": reply_msg,
                        "follow_up_suggestions": follow_up_suggestions,
                        "charge": charge_payload,
                    }
                    yield _format_sse("done", done_data)
                    continue

                yield _format_sse(event, data)
        except ValueError as e:
            yield _format_sse("error", {"message": str(e)})
        except Exception as e:
            logger.error("问股流式处理失败: %s", e, exc_info=True)
            yield _format_sse("error", {"message": f"问股失败: {e}"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get("/chat/sessions/{session_id}/follow-ups")
async def mp_get_follow_up_suggestions(
    session_id: str,
    user: dict = Depends(get_current_mp_user),
):
    """基于最近一轮问答生成继续追问建议（恢复会话时用）"""
    chat_session = await mp_chat_service.get_session_for_user(user["id"], session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = await mp_chat_service.list_messages(session_id)
    suggestions = chat_suggestion_service.from_messages(
        messages,
        stock_code=chat_session.stock_code,
        strategy_id=chat_session.strategy_id,
    )
    return {"success": True, "data": {"follow_up_suggestions": suggestions}}
