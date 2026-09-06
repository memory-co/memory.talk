"""/api/servers —— 有哪些 server、各自响应哪些协议。寻址在 open 时自动发生,没有单独的端点。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from models.server import ServerInfo
from services.servers import ServerService

router = APIRouter(prefix="/api/servers", tags=["servers"])


def servers(request: Request) -> ServerService:
    return request.app.state.servers


@router.get("", response_model=list[ServerInfo], summary="server 清单及各自响应的协议")
def list_servers(svc: ServerService = Depends(servers)):
    return svc.list()
