"""小程序问股数据模型"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ChatStrategy(BaseModel):
    id: str
    name: str
    description: str = ""


class ChatSessionCreate(BaseModel):
    title: Optional[str] = None
    stock_code: Optional[str] = None
    strategy_id: str = "bull_trend"


class ChatAskRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    strategy_id: Optional[str] = None


class ChatMessageItem(BaseModel):
    id: str
    role: str
    content: str
    stock_code: Optional[str] = None
    status: str = "completed"
    error_message: Optional[str] = None
    created_at: str


class ChatSessionItem(BaseModel):
    session_id: str
    user_id: str
    user_nickname: str = ""
    user_openid: str = ""
    title: str
    stock_code: Optional[str] = None
    strategy_id: str
    status: str
    message_count: int
    created_at: str
    updated_at: str
    last_message: str = ""


class ChatSessionDetail(ChatSessionItem):
    messages: List[ChatMessageItem] = Field(default_factory=list)


class ChatAskResponse(BaseModel):
    session_id: str
    message: ChatMessageItem
    reply: ChatMessageItem
    charge: Optional[dict] = None
