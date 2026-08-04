"""问股完成后追问建议生成"""

import re
from typing import List, Optional, Sequence, Tuple

STOCK_CODE_RE = re.compile(r"(?<![\d.])(\d{6})(?![\d.])")

_TOPIC_RULES: Sequence[Tuple[Tuple[str, ...], Tuple[str, ...]]] = (
    (
        ("技术", "均线", "macd", "kdj", "趋势", "量价", "突破", "回调"),
        (
            "成交量变化说明什么？",
            "当前趋势还能持续吗？",
            "关键支撑位在哪里？",
        ),
    ),
    (
        ("基本面", "业绩", "财报", "估值", "pe", "净利", "营收", "roe"),
        (
            "估值处于什么水平？",
            "业绩增速如何评价？",
            "行业景气度怎样？",
        ),
    ),
    (
        ("买", "卖", "操作", "建仓", "加仓", "减仓", "持仓", "仓位"),
        (
            "具体买点怎么把握？",
            "分批建仓如何规划？",
            "止损位设在哪里？",
        ),
    ),
    (
        ("风险", "利空", "跌", "暴雷", "监管", "减持"),
        (
            "最大下行风险在哪？",
            "有哪些潜在利空？",
            "出现什么信号应离场？",
        ),
    ),
)

_WITH_STOCK: Tuple[str, ...] = (
    "{label}压力位和支撑位在哪？",
    "{label}主力资金动向如何？",
    "{label}短期还有上涨空间吗？",
    "如果继续持有，止盈止损怎么设？",
    "同行业对比有什么优劣势？",
)

_GENERIC: Tuple[str, ...] = (
    "风险点主要有哪些？",
    "短期操作建议是什么？",
    "消息面有什么需要关注？",
    "和板块龙头比如何？",
)


def _stock_label(stock_code: Optional[str]) -> str:
    return stock_code if stock_code else "这只股票"


def _topic_suggestions(text: str) -> List[str]:
    lowered = text.lower()
    for keywords, items in _TOPIC_RULES:
        if any(keyword in lowered for keyword in keywords):
            return list(items)
    return []


def _dedupe_limit(items: List[str], limit: int = 4) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        text = (item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


class ChatSuggestionService:
    def generate(
        self,
        *,
        stock_code: Optional[str],
        user_message: str,
        assistant_reply: str,
        strategy_id: Optional[str] = None,
    ) -> List[str]:
        if not assistant_reply or assistant_reply.startswith("[分析失败]"):
            return []

        code = stock_code or self._extract_code(user_message, assistant_reply)
        label = _stock_label(code)
        combined = f"{user_message}\n{assistant_reply}"

        pool: List[str] = []
        pool.extend(_topic_suggestions(combined))

        if code:
            pool.extend(tpl.format(label=label) for tpl in _WITH_STOCK)
        else:
            pool.extend(_GENERIC)

        if strategy_id in {"bull_trend", "momentum"}:
            pool.append("趋势走弱时如何应对？")
        elif strategy_id in {"value_invest", "fundamental"}:
            pool.append("从基本面看还值得持有吗？")
        elif strategy_id in {"short_term", "swing"}:
            pool.append("短线交易节奏怎么把握？")

        pool.extend(_GENERIC)
        return _dedupe_limit(pool, 4)

    @staticmethod
    def _extract_code(user_message: str, assistant_reply: str) -> Optional[str]:
        for text in (user_message, assistant_reply):
            match = STOCK_CODE_RE.search(text or "")
            if match:
                return match.group(1)
        return None

    def from_messages(
        self,
        messages: List[dict],
        *,
        stock_code: Optional[str] = None,
        strategy_id: Optional[str] = None,
    ) -> List[str]:
        if not messages:
            return []
        last = messages[-1]
        if last.get("role") != "assistant" or last.get("status") != "completed":
            return []
        user_msg = ""
        for item in reversed(messages[:-1]):
            if item.get("role") == "user":
                user_msg = item.get("content") or ""
                break
        code = stock_code or last.get("stock_code")
        return self.generate(
            stock_code=code,
            user_message=user_msg,
            assistant_reply=last.get("content") or "",
            strategy_id=strategy_id,
        )


chat_suggestion_service = ChatSuggestionService()
