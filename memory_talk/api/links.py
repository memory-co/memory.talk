from __future__ import annotations
from fastapi import APIRouter, Request, Query
from memory_talk.models.link import LinkCreate
from memory_talk.service.links import LinksService

router = APIRouter()

@router.post("/links")
def create_link(body: LinkCreate, request: Request):
    svc = LinksService(request.app.state.config)
    return svc.create(body.model_dump())

@router.get("/links")
def list_links(request: Request, id: str = Query(...), type: str | None = Query(None)):
    svc = LinksService(request.app.state.config)
    return svc.list_links(id, type_filter=type)

@router.delete("/links/{link_id}")
def delete_link(link_id: str, request: Request):
    svc = LinksService(request.app.state.config)
    return svc.delete(link_id)
