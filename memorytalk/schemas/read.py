"""POST /v3/read — request + response."""
from __future__ import annotations
from typing import Literal, Union

from pydantic import BaseModel, Field

from memorytalk.schemas.card import Card
from memorytalk.schemas.session import Session


class ReadRequest(BaseModel):
    id: str


class _ReadCardResponse(BaseModel):
    type: Literal["card"] = "card"
    read_at: str
    card: Card


class _ReadSessionResponse(BaseModel):
    type: Literal["session"] = "session"
    read_at: str
    session: Session


# Discriminated union: type=card → has `card`; type=session → has `session`.
ReadResponse = Union[_ReadCardResponse, _ReadSessionResponse]
