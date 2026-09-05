"""/api/servers —— 有哪些 server、一个 URI 会请求到谁。建现场走 /api/tasks/{id}/members。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from models.server import ParsedUri, ServerInfo
from services.servers import ServerService

router = APIRouter(prefix="/api/servers", tags=["servers"])


def servers(request: Request) -> ServerService:
    return request.app.state.servers


@router.get("", response_model=list[ServerInfo], summary="server 清单及各自认领的协议")
def list_servers(svc: ServerService = Depends(servers)):
    return svc.list()


@router.get("/resolve", summary="这个 URI 会请求到哪个 server(不建现场)")
def resolve(uri: str, svc: ServerService = Depends(servers)) -> dict:
    parsed, server = svc.resolve(uri)
    return {"uri": ParsedUri.model_validate(parsed).model_dump(), "server": server.name}
