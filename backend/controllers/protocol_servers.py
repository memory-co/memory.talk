"""/api/protocol-servers —— 有哪些 server、各自响应哪些协议。寻址在 open 时自动发生,没有单独的端点。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from models.protocol_server import ProtocolServerInfo
from services.protocol_servers import ProtocolServerService

router = APIRouter(prefix="/api/protocol-servers", tags=["servers"])


def protocol_servers(request: Request) -> ProtocolServerService:
    return request.app.state.protocol_servers


@router.get("", response_model=list[ProtocolServerInfo], summary="server 清单及各自响应的协议")
def list_servers(svc: ProtocolServerService = Depends(protocol_servers)):
    return svc.list()
