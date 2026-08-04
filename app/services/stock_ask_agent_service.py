"""问股 Agent 服务（daily_stock_analysis 物理迁入 app/stock_agent）"""

import asyncio
import os
import re
from typing import Callable, Dict, List, Optional

try:
    from tradingagents.utils.logging_manager import get_logger
except ImportError:
    import logging

    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)

logger = get_logger("stock_ask_agent")

STOCK_CODE_RE = re.compile(r"(?<![\d.])(\d{6})(?![\d.])")


class StockAskAgentService:
    def __init__(self) -> None:
        self._strategies_cache: Optional[List[Dict[str, str]]] = None
        self._ensure_agent_env()

    @staticmethod
    def _ensure_agent_env() -> None:
        os.environ.setdefault("AGENT_MODE", "true")

    def list_strategies(self) -> List[Dict[str, str]]:
        if self._strategies_cache is not None:
            return self._strategies_cache
        from app.stock_agent.agent.factory import get_skill_manager
        from app.stock_agent.dsa_config import get_config

        skill_manager = get_skill_manager(get_config())
        items = [
            {
                "id": skill.name,
                "name": skill.display_name,
                "description": skill.description,
                "instructions": skill.instructions,
            }
            for skill in skill_manager.list_skills()
        ]
        self._strategies_cache = items
        return items

    def get_strategy(self, strategy_id: str) -> Dict[str, str]:
        for item in self.list_strategies():
            if item["id"] == strategy_id:
                return item
        strategies = self.list_strategies()
        return strategies[0] if strategies else {"id": "bull_trend", "name": "默认策略", "description": "", "instructions": ""}

    @staticmethod
    def extract_stock_code(text: str) -> Optional[str]:
        if not text:
            return None
        match = STOCK_CODE_RE.search(text.strip())
        return match.group(1) if match else None

    def _run_agent_sync(
        self,
        *,
        user_message: str,
        strategy_id: str,
        stock_code: Optional[str],
        history: List[Dict[str, str]],
        progress_callback: Optional[Callable[[Dict], None]] = None,
    ) -> str:
        from app.stock_agent.agent.factory import build_agent_executor

        skills = [strategy_id] if strategy_id else None
        executor = build_agent_executor(skills=skills)
        context = {"stock_code": stock_code} if stock_code else None
        result = executor.chat_with_history(
            message=user_message,
            history=history,
            context=context,
            progress_callback=progress_callback,
        )
        if result.success and result.content:
            return result.content.strip()
        if result.content:
            return result.content.strip()
        raise ValueError(result.error or "问股 Agent 未返回有效内容")

    async def ask(
        self,
        *,
        user_message: str,
        strategy_id: str,
        stock_code: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        progress_callback: Optional[Callable[[Dict], None]] = None,
    ) -> str:
        history = history or []
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._run_agent_sync(
                user_message=user_message,
                strategy_id=strategy_id,
                stock_code=stock_code,
                history=history,
                progress_callback=progress_callback,
            ),
        )


stock_ask_agent_service = StockAskAgentService()
