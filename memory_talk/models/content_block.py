"""Content block types for conversation rounds."""

from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel


class TextBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str


class CodeBlock(BaseModel):
    type: Literal["code"] = "code"
    language: str
    text: str


class ToolUseBlock(BaseModel):
    type: Literal["tool_use"] = "tool_use"
    name: str
    input: str


class ToolResultBlock(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    output: str


ContentBlock = Union[TextBlock, CodeBlock, ToolUseBlock, ToolResultBlock]
