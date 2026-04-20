from __future__ import annotations
from fastapi import APIRouter, Request
from pydantic import BaseModel

class RecallRequest(BaseModel):
    query: str
    top_k: int = 5

router = APIRouter()

@router.post("/recall")
def recall(body: RecallRequest, request: Request):
    from memory_talk.service.recall import RecallService
    svc = RecallService(request.app.state.config)
    return svc.recall(body.query, body.top_k)
