"""/api/collections —— 认知层:层、树、检索、manager、对象 CRUD、历史、行为。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import PlainTextResponse

from models.collections import (CatalogDir, InboxItem, LayerCreate, LayerInfo, Manager, ManagerPut, Obj,
                            ObjCreate, ObjUpdate, Revision, SearchHit, TreeItem)
from services.collections import CollectionsError, CollectionsService, Ctx

router = APIRouter(prefix="/api/collections", tags=["collections"])


def collections(request: Request) -> CollectionsService:
    return request.app.state.collections


def ctx(x_memory_talk_user: str | None = Header(None, alias="X-Memory-Talk-User"),
        x_memory_talk_work: str | None = Header(None, alias="X-Memory-Talk-Work")) -> Ctx:
    return Ctx(user=x_memory_talk_user, work=x_memory_talk_work)


# ---- 固定路径先于 /{layer} ----

@router.get("/layers", response_model=list[LayerInfo], summary="有哪些层(最底在前)、各自的 schema 与行为")
def layers(svc: CollectionsService = Depends(collections)):
    return svc.layer_infos()


@router.post("/layers", response_model=LayerInfo, status_code=201, summary="加一个用户层:一份 schema YAML")
def add_layer(req: LayerCreate, svc: CollectionsService = Depends(collections), c: Ctx = Depends(ctx)):
    return svc.add_layer(req.name, req.schema_yaml, req.reason, c)


@router.get("/tree", response_model=list[TreeItem], summary="浏览目录树:对象(带后缀的目录折成一项)、目录、origin 文件")
def tree(path: str = "", svc: CollectionsService = Depends(collections)):
    return svc.tree(path)


@router.get("/search", response_model=list[SearchHit], summary="git grep 整个 Collections(可限定层)")
def search(q: str, layer: str | None = None, svc: CollectionsService = Depends(collections)):
    return svc.search(q, layer)


@router.get("/manager", response_model=Manager | None, summary="这个路径归谁管(最近的 manager.json)")
def get_manager(path: str = "", svc: CollectionsService = Depends(collections)):
    return svc.manager(path)


@router.put("/manager", response_model=Manager, summary="在这个目录(或对象)下放 manager.json,绑到一个 work")
def put_manager(req: ManagerPut, path: str = "", svc: CollectionsService = Depends(collections), c: Ctx = Depends(ctx)):
    return svc.set_manager(path, req.work, req.reason, c)


@router.delete("/manager", status_code=204, summary="解绑:删这个目录的 manager.json")
def delete_manager(path: str = "", reason: str = "", svc: CollectionsService = Depends(collections), c: Ctx = Depends(ctx)):
    svc.unset_manager(path, reason, c)


@router.get("/managed", response_model=list[TreeItem], summary="某个 work 管的所有对象;不传 work = 没人管的对象")
def managed(work: str | None = None, svc: CollectionsService = Depends(collections)):
    return svc.managed_by(work) if work else svc.unmanaged()


@router.get("/history/{layer}/{path:path}", response_model=list[Revision], summary="一个对象的 git log(这一层的分支上)")
def history(layer: str, path: str, svc: CollectionsService = Depends(collections)):
    return svc.history(layer, path)


@router.post("/act/{layer}/{action}/{path:path}", summary="行为:schema 之上的领域动作(issue: position / argue / link / spawn / decide;card: discuss)")
def act(layer: str, action: str, path: str, payload: dict[str, Any], svc: CollectionsService = Depends(collections),
        c: Ctx = Depends(ctx)) -> Any:
    return svc.act(layer, action, path, payload, c)


# ---- 层级 / 对象 ----

@router.get("/{layer}", response_model=CatalogDir, summary="一层的目录(按目录树列标题)")
def catalog(layer: str, dir: str = "", svc: CollectionsService = Depends(collections)):
    return svc.catalog(layer, dir)


@router.get("/{layer}/recall", response_class=PlainTextResponse, summary="目录渲染成可注入 agent 的文本")
def recall(layer: str, dir: str = "", svc: CollectionsService = Depends(collections)):
    return svc.recall_text(layer, dir)


@router.post("/{layer}/{path:path}", response_model=Obj, status_code=201, summary="建一个对象(一个 [layer] 提交)")
def create(layer: str, path: str, req: ObjCreate, svc: CollectionsService = Depends(collections), c: Ctx = Depends(ctx)):
    data = req.content if svc.layer(layer).format == "raw" else (req.data or {})
    return svc.create(layer, path, data, req.reason, c)


@router.get("/{layer}/{path:path}", response_model=Obj, summary="读一个对象(rev= 读历史版本)")
def get(layer: str, path: str, rev: str | None = Query(None), svc: CollectionsService = Depends(collections)):
    return svc.get(layer, path, rev)


@router.put("/{layer}/{path:path}", response_model=Obj, summary="改一个对象(字段合并;origin 整体替换)")
def update(layer: str, path: str, req: ObjUpdate, svc: CollectionsService = Depends(collections), c: Ctx = Depends(ctx)):
    patch = req.content if svc.layer(layer).format == "raw" else (req.data or {})
    return svc.update(layer, path, patch, req.reason, c)


@router.delete("/{layer}/{path:path}", status_code=204, summary="删一个对象(历史在 git)")
def delete(layer: str, path: str, reason: str = "", svc: CollectionsService = Depends(collections), c: Ctx = Depends(ctx)):
    svc.delete(layer, path, reason, c)
