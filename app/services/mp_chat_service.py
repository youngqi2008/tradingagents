"""小程序问股会话服务"""

import asyncio
import uuid
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from sqlalchemy import desc, func, or_, select

from app.core.mysql_db import get_mysql_session, mysql_session, parse_int_id
from app.models.sql.models import MpChatMessageORM, MpChatSessionORM
from app.services.stock_ask_agent_service import stock_ask_agent_service
from app.services.user_service import user_service
from app.utils.timezone import now_tz, to_config_tz

try:
    from tradingagents.utils.logging_manager import get_logger
except ImportError:
    import logging

    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)

logger = get_logger("mp_chat_service")


def _fmt_dt(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        dt = to_config_tz(value)
        return dt.isoformat()
    return str(value)


class MpChatService:
    async def create_session(
        self,
        user_id: str,
        *,
        title: Optional[str] = None,
        stock_code: Optional[str] = None,
        strategy_id: str = "bull_trend",
    ) -> dict:
        uid = parse_int_id(user_id)
        if not uid:
            raise ValueError("用户不存在")
        session_id = str(uuid.uuid4())
        display_title = (title or "").strip() or (f"问股 {stock_code}" if stock_code else "新问股")
        async with get_mysql_session() as session:
            row = MpChatSessionORM(
                session_id=session_id,
                user_id=uid,
                title=display_title[:256],
                stock_code=stock_code,
                strategy_id=strategy_id or "bull_trend",
                status="active",
                message_count=0,
            )
            session.add(row)
            await session.flush()
            await session.refresh(row)
            return self._serialize_session(row)

    async def get_session_for_user(self, user_id: str, session_id: str) -> Optional[MpChatSessionORM]:
        uid = parse_int_id(user_id)
        if not uid:
            return None
        async with mysql_session() as session:
            result = await session.execute(
                select(MpChatSessionORM).where(
                    MpChatSessionORM.session_id == session_id,
                    MpChatSessionORM.user_id == uid,
                    MpChatSessionORM.status != "deleted",
                )
            )
            return result.scalar_one_or_none()

    async def list_user_sessions(self, user_id: str, *, limit: int = 50) -> List[dict]:
        uid = parse_int_id(user_id)
        if not uid:
            return []
        async with mysql_session() as session:
            result = await session.execute(
                select(MpChatSessionORM)
                .where(MpChatSessionORM.user_id == uid, MpChatSessionORM.status != "deleted")
                .order_by(desc(MpChatSessionORM.updated_at))
                .limit(limit)
            )
            rows = result.scalars().all()
            return [self._serialize_session(r) for r in rows]

    async def list_messages(self, session_id: str, *, limit: int = 100) -> List[dict]:
        async with mysql_session() as session:
            result = await session.execute(
                select(MpChatMessageORM)
                .where(MpChatMessageORM.session_id == session_id)
                .order_by(MpChatMessageORM.id.asc())
                .limit(limit)
            )
            return [self._serialize_message(r) for r in result.scalars().all()]

    async def delete_session(self, user_id: str, session_id: str) -> bool:
        uid = parse_int_id(user_id)
        if not uid:
            return False
        async with get_mysql_session() as session:
            result = await session.execute(
                select(MpChatSessionORM).where(
                    MpChatSessionORM.session_id == session_id,
                    MpChatSessionORM.user_id == uid,
                )
            )
            row = result.scalar_one_or_none()
            if not row:
                return False
            row.status = "deleted"
            row.updated_at = now_tz()
            return True

    async def ask_in_session(
        self,
        user_id: str,
        session_id: str,
        message: str,
        *,
        strategy_id: Optional[str] = None,
    ) -> Tuple[dict, dict]:
        chat_session = await self.get_session_for_user(user_id, session_id)
        if not chat_session:
            raise ValueError("会话不存在")
        if chat_session.status == "disabled":
            raise ValueError("该问股会话已被禁用，请联系客服")
        if chat_session.status != "active":
            raise ValueError("会话不可用")

        uid = parse_int_id(user_id)
        assert uid is not None
        active_strategy = strategy_id or chat_session.strategy_id
        stock_code = chat_session.stock_code or stock_ask_agent_service.extract_stock_code(message)
        history = await self.list_messages(session_id)

        user_msg_row: Optional[MpChatMessageORM] = None
        async with get_mysql_session() as session:
            user_msg_row = MpChatMessageORM(
                session_id=session_id,
                user_id=uid,
                role="user",
                content=message.strip(),
                stock_code=stock_code,
                status="completed",
            )
            session.add(user_msg_row)
            await session.flush()
            await session.refresh(user_msg_row)

        try:
            answer = await stock_ask_agent_service.ask(
                user_message=message.strip(),
                strategy_id=active_strategy,
                stock_code=stock_code,
                history=history,
            )
            assistant_status = "completed"
            error_message = None
        except Exception as e:
            logger.error("问股失败 session=%s: %s", session_id, e, exc_info=True)
            answer = f"[分析失败] {e}"
            assistant_status = "failed"
            error_message = str(e)

        async with get_mysql_session() as session:
            result = await session.execute(
                select(MpChatSessionORM).where(MpChatSessionORM.session_id == session_id)
            )
            sess = result.scalar_one_or_none()
            if sess:
                if stock_code and not sess.stock_code:
                    sess.stock_code = stock_code
                if strategy_id:
                    sess.strategy_id = active_strategy
                if sess.title in ("新问股", "") and message.strip():
                    sess.title = message.strip()[:30]
                sess.message_count = (sess.message_count or 0) + 2
                sess.updated_at = now_tz()

            assistant_row = MpChatMessageORM(
                session_id=session_id,
                user_id=uid,
                role="assistant",
                content=answer,
                stock_code=stock_code,
                status=assistant_status,
                error_message=error_message,
            )
            session.add(assistant_row)
            await session.flush()
            await session.refresh(assistant_row)
            return self._serialize_message(user_msg_row), self._serialize_message(assistant_row)

    async def stream_ask_in_session(
        self,
        user_id: str,
        session_id: str,
        message: str,
        *,
        strategy_id: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """流式问股：产出 user_message / progress / assistant_done / error 事件。"""
        chat_session = await self.get_session_for_user(user_id, session_id)
        if not chat_session:
            raise ValueError("会话不存在")
        if chat_session.status == "disabled":
            raise ValueError("该问股会话已被禁用，请联系客服")
        if chat_session.status != "active":
            raise ValueError("会话不可用")

        uid = parse_int_id(user_id)
        assert uid is not None
        active_strategy = strategy_id or chat_session.strategy_id
        stock_code = chat_session.stock_code or stock_ask_agent_service.extract_stock_code(message)
        history = await self.list_messages(session_id)
        trimmed_message = message.strip()

        user_msg_row: Optional[MpChatMessageORM] = None
        async with get_mysql_session() as session:
            user_msg_row = MpChatMessageORM(
                session_id=session_id,
                user_id=uid,
                role="user",
                content=trimmed_message,
                stock_code=stock_code,
                status="completed",
            )
            session.add(user_msg_row)
            await session.flush()
            await session.refresh(user_msg_row)

        user_msg = self._serialize_message(user_msg_row)
        yield {"event": "user_message", "data": {"message": user_msg}}

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def on_progress(payload: Dict[str, Any]) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, ("progress", payload))

        async def run_agent() -> None:
            try:
                answer = await stock_ask_agent_service.ask(
                    user_message=trimmed_message,
                    strategy_id=active_strategy,
                    stock_code=stock_code,
                    history=history,
                    progress_callback=on_progress,
                )
                await queue.put(("success", answer))
            except Exception as e:
                logger.error("流式问股失败 session=%s: %s", session_id, e, exc_info=True)
                await queue.put(("error", str(e)))

        agent_task = asyncio.create_task(run_agent())

        answer: Optional[str] = None
        assistant_status = "completed"
        error_message: Optional[str] = None

        while True:
            if agent_task.done() and queue.empty():
                break
            try:
                kind, payload = await asyncio.wait_for(queue.get(), timeout=15.0)
            except asyncio.TimeoutError:
                yield {"event": "heartbeat", "data": {"timestamp": asyncio.get_running_loop().time()}}
                continue

            if kind == "progress":
                yield {"event": "progress", "data": payload}
            elif kind == "success":
                answer = str(payload)
                break
            elif kind == "error":
                answer = f"[分析失败] {payload}"
                assistant_status = "failed"
                error_message = str(payload)
                break

        if answer is None:
            answer = "[分析失败] 问股 Agent 未返回有效内容"
            assistant_status = "failed"
            error_message = answer

        async with get_mysql_session() as session:
            result = await session.execute(
                select(MpChatSessionORM).where(MpChatSessionORM.session_id == session_id)
            )
            sess = result.scalar_one_or_none()
            if sess:
                if stock_code and not sess.stock_code:
                    sess.stock_code = stock_code
                if strategy_id:
                    sess.strategy_id = active_strategy
                if sess.title in ("新问股", "") and trimmed_message:
                    sess.title = trimmed_message[:30]
                sess.message_count = (sess.message_count or 0) + 2
                sess.updated_at = now_tz()

            assistant_row = MpChatMessageORM(
                session_id=session_id,
                user_id=uid,
                role="assistant",
                content=answer,
                stock_code=stock_code,
                status=assistant_status,
                error_message=error_message,
            )
            session.add(assistant_row)
            await session.flush()
            await session.refresh(assistant_row)

        yield {
            "event": "assistant_done",
            "data": {
                "message": user_msg,
                "reply": self._serialize_message(assistant_row),
                "stock_code": stock_code,
                "strategy_id": active_strategy,
            },
        }

    async def list_sessions_admin(
        self,
        *,
        skip: int = 0,
        limit: int = 20,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> Tuple[List[dict], int]:
        user_map = await user_service.get_mp_user_id_map()
        async with mysql_session() as session:
            query = select(MpChatSessionORM).where(MpChatSessionORM.status != "deleted")
            count_query = select(func.count()).select_from(MpChatSessionORM).where(
                MpChatSessionORM.status != "deleted"
            )
            if user_id:
                uid = parse_int_id(user_id)
                if uid:
                    query = query.where(MpChatSessionORM.user_id == uid)
                    count_query = count_query.where(MpChatSessionORM.user_id == uid)
            if status:
                query = query.where(MpChatSessionORM.status == status)
                count_query = count_query.where(MpChatSessionORM.status == status)
            if keyword:
                kw = f"%{keyword.strip()}%"
                query = query.where(
                    or_(
                        MpChatSessionORM.title.like(kw),
                        MpChatSessionORM.session_id.like(kw),
                        MpChatSessionORM.stock_code.like(kw),
                    )
                )
                count_query = count_query.where(
                    or_(
                        MpChatSessionORM.title.like(kw),
                        MpChatSessionORM.session_id.like(kw),
                        MpChatSessionORM.stock_code.like(kw),
                    )
                )
            total = (await session.execute(count_query)).scalar() or 0
            result = await session.execute(
                query.order_by(desc(MpChatSessionORM.updated_at)).offset(skip).limit(limit)
            )
            rows = result.scalars().all()
            items = []
            for row in rows:
                item = self._serialize_session(row, user_map.get(str(row.user_id), {}))
                last_msg = await session.execute(
                    select(MpChatMessageORM)
                    .where(MpChatMessageORM.session_id == row.session_id)
                    .order_by(desc(MpChatMessageORM.id))
                    .limit(1)
                )
                last = last_msg.scalar_one_or_none()
                item["last_message"] = (last.content[:120] if last and last.content else "")
                items.append(item)
            return items, int(total)

    async def get_session_admin(self, session_id: str) -> Optional[dict]:
        user_map = await user_service.get_mp_user_id_map()
        async with mysql_session() as session:
            result = await session.execute(
                select(MpChatSessionORM).where(
                    MpChatSessionORM.session_id == session_id,
                    MpChatSessionORM.status != "deleted",
                )
            )
            row = result.scalar_one_or_none()
            if not row:
                return None
            data = self._serialize_session(row, user_map.get(str(row.user_id), {}))
            msgs = await session.execute(
                select(MpChatMessageORM)
                .where(MpChatMessageORM.session_id == session_id)
                .order_by(MpChatMessageORM.id.asc())
            )
            data["messages"] = [self._serialize_message(m) for m in msgs.scalars().all()]
            return data

    async def set_session_status_admin(self, session_id: str, status: str) -> bool:
        if status not in {"active", "disabled", "deleted"}:
            return False
        async with get_mysql_session() as session:
            result = await session.execute(
                select(MpChatSessionORM).where(MpChatSessionORM.session_id == session_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                return False
            row.status = status
            row.updated_at = now_tz()
            return True

    def _serialize_session(self, row: MpChatSessionORM, user_info: Optional[dict] = None) -> dict:
        user_info = user_info or {}
        return {
            "session_id": row.session_id,
            "user_id": str(row.user_id),
            "user_nickname": user_info.get("nickname", ""),
            "user_openid": user_info.get("openid", ""),
            "title": row.title,
            "stock_code": row.stock_code,
            "strategy_id": row.strategy_id,
            "status": row.status,
            "message_count": row.message_count or 0,
            "created_at": _fmt_dt(row.created_at),
            "updated_at": _fmt_dt(row.updated_at),
        }

    def _serialize_message(self, row: MpChatMessageORM) -> dict:
        return {
            "id": str(row.id),
            "role": row.role,
            "content": row.content,
            "stock_code": row.stock_code,
            "status": row.status,
            "error_message": row.error_message,
            "created_at": _fmt_dt(row.created_at),
        }


mp_chat_service = MpChatService()
