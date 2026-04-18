"""Session data model — raw conversation from platforms."""
from __future__ import annotations
from datetime import datetime
from typing import Any, Literal, Optional, Union
from pydantic import BaseModel

class TextBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str

class CodeBlock(BaseModel):
    type: Literal["code"] = "code"
    language: str
    text: str

class ThinkingBlock(BaseModel):
    type: Literal["thinking"] = "thinking"
    thinking: str

ContentBlock = Union[TextBlock, CodeBlock, ThinkingBlock]

class Usage(BaseModel):
    input_tokens: int
    output_tokens: int

class Round(BaseModel):
    round_id: str
    parent_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    speaker: str
    role: str
    content: list[ContentBlock]
    is_sidechain: bool = False
    cwd: Optional[str] = None
    usage: Optional[Usage] = None

class Session(BaseModel):
    session_id: str
    source: str
    created_at: Optional[datetime] = None
    metadata: dict[str, Any] = {}
    tags: list[str] = []
    rounds: list[Round] = []
    round_count: int = 0
    synced_at: Optional[datetime] = None
