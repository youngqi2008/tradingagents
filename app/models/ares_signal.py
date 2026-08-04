"""外部买卖点信号推送模型"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class AresSignalTextBody(BaseModel):
    content: str = Field(..., min_length=1)


class AresSignalWebhook(BaseModel):
    msgtype: Literal["text"] = "text"
    text: AresSignalTextBody


class AresSignalParsed(BaseModel):
    signal_type: Literal["buy", "sell"]
    stock_code: str
    market: Optional[str] = None
    signal_time: Optional[str] = None
    raw_content: str
