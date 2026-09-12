"""/api/collections —— 认知层:层、树、检索、对象(目录里的一组文件)CRUD、历史、行为。"""
from __future__ import annotations

from typing import Any

from memorytalk.backend.models.result import Result, ok
from fastapi import APIRouter, Depends, Header, Query, Request

from memorytalk.backend.models.collections import (CatalogDir, InboxItem, LayerCreate, LayerInfo, Manager, ManagerPut, Obj,
                            ObjCreate, ObjUpdate, Revision, SearchHit, TreeItem)
from memorytalk.backend.services.collections import CollectionsError, CollectionsService, Ctx

router = APIRouter(prefix="/api/collections", tags=["collections"])


def collections(request: Request) -> CollectionsService:
    return request.app.state.collections


def ctx(request: Request, x_memory_talk_user: str | None = Header(None, alias="X-Memory-Talk-User"),
        x_memory_talk_work: str | None = Header(None, alias="X-Memory-Talk-Work")) -> Ctx:
    if x_memory_talk_user:
        request.app.state.users.get(x_memory_talk_user)        # 未注册 → 404 not_found
    return Ctx(user=x_memory_talk_user, work=x_memory_talk_work)


# ---- 固定路径先于 /{layer} ----

@router.get("/layers", response_model=Result[list[LayerInfo]], summary="有哪些层(最底在前)、各自的 schema 与行为")
def layers(svc: CollectionsService = Depends(collections)):
    return ok(svc.layer_infos())


@router.post("/layers", response_model=Result[LayerInfo], status_code=201, summary="加一个用户层:一份 schema YAML")
def add_layer(req: LayerCreate, svc: CollectionsService = Depends(collections), c: Ctx = Depends(ctx)):
    return ok(svc.add_layer(req.name, req.schema_yaml, req.reason, c))


@router.get("/config", summary="collections.json 本体 + 它的 git 历史(层的变化史)", response_model=Result[dict])
def config(svc: CollectionsService = Depends(collections)) -> dict:
    return ok({"config": svc.anchor(), "history": [r.model_dump() for r in svc.anchor_history()]})


@router.get("/tree", response_model=Result[list[TreeItem]], summary="浏览目录树:对象(带后缀的目录折成一项)、目录、origin 文件")
def tree(path: str = "", svc: CollectionsService = Depends(collections)):
    return ok(svc.tree(path))


@router.get("/search", response_model=Result[list[SearchHit]], summary="git grep 整个 Collections(可限定层)")
def search(q: str, layer: str | None = None, svc: CollectionsService = Depends(collections)):
    return ok(svc.search(q, layer))


# ---- manager / managed:先注释掉,等 work 那边实现了再一起搞(service 里 svc.manager / set_manager / unset_manager / managed_by / unmanaged 都还在) ----
# @router.get("/manager", response_model=Result[Manager | None], summary="这个路径归谁管(最近的 manager.json)")
# def get_manager(path: str = "", svc: CollectionsService = Depends(collections)):
#     return ok(svc.manager(path))
#
#
# @router.put("/manager", response_model=Result[Manager], summary="在这个目录(或对象)下放 manager.json,绑到一个 work")
# def put_manager(req: ManagerPut, path: str = "", svc: CollectionsService = Depends(collections), c: Ctx = Depends(ctx)):
#     return ok(svc.set_manager(path, req.work, req.reason, c))
#
#
# @router.delete("/manager", summary="解绑:删这个目录的 manager.json")
# def delete_manager(path: str = "", reason: str = "", svc: CollectionsService = Depends(collections), c: Ctx = Depends(ctx)):
#     svc.unset_manager(path, reason, c)
#     return ok()
#
#
# @router.get("/managed", response_model=Result[list[TreeItem]], summary="某个 work 管的所有对象;不传 work = 没人管的对象")
# def managed(work: str | None = None, svc: CollectionsService = Depends(collections)):
#     return ok(svc.managed_by(work) if work else svc.unmanaged())


@router.get("/history/{layer}/{path:path}", response_model=Result[list[Revision]], summary="一个对象的 git log(这一层的分支上)")
def history(layer: str, path: str, svc: CollectionsService = Depends(collections)):
    return ok(svc.history(layer, path))


@router.post("/act/{layer}/{action}/{path:path}", summary="行为:校验器之上的快捷方式(issue: position / argue / link / rank;card: discuss)")
def act(layer: str, action: str, path: str, payload: dict[str, Any], svc: CollectionsService = Depends(collections),
        c: Ctx = Depends(ctx)) -> Any:
    return ok(svc.act(layer, action, path, payload, c))


# ---- 层级 / 对象 ----

@router.get("/{layer}", response_model=Result[CatalogDir], summary="一层的目录(按目录树列标题)")
def catalog(layer: str, dir: str = "", svc: CollectionsService = Depends(collections)):
    return ok(svc.catalog(layer, dir))


def _files(svc: CollectionsService, layer: str, path: str, req: ObjCreate | ObjUpdate, merge: bool) -> dict:
    """请求体 → 目录里的文件改动:origin 用 content;files 直接给;data 是单字段文件层的简写。"""
    spec = svc.layer(layer)
    if spec.raw:
        if req.content is None:
            raise CollectionsError("invalid", "origin 要给 content", 400)
        return {"": req.content}
    files: dict = dict(req.files or {})
    if req.data is not None:
        files.update(svc.files_from_data(layer, path, req.data, merge))
    return files


@router.post("/{layer}/{path:path}", response_model=Result[Obj], status_code=201,
             summary="建一个对象:目录里的文件(files)或字段简写(data);origin 用 content。整目录按层的 schema 校验,一个 [layer] 提交")
def create(layer: str, path: str, req: ObjCreate, svc: CollectionsService = Depends(collections), c: Ctx = Depends(ctx)):
    return ok(svc.create(layer, path, _files(svc, layer, path, req, merge=False), req.reason, c))


@router.get("/{layer}/{path:path}", response_model=Result[Obj], summary="读一个对象(rev= 读历史版本)")
def get(layer: str, path: str, rev: str | None = Query(None), svc: CollectionsService = Depends(collections)):
    return ok(svc.get(layer, path, rev))


@router.put("/{layer}/{path:path}", response_model=Result[Obj],
            summary="改一个对象:files 加 / 改 / 删(null)目录里的文件,没提到的不动;data 是字段合并;origin 整体替换")
def update(layer: str, path: str, req: ObjUpdate, svc: CollectionsService = Depends(collections), c: Ctx = Depends(ctx)):
    return ok(svc.update(layer, path, _files(svc, layer, path, req, merge=True), req.reason, c))


@router.delete("/{layer}/{path:path}", summary="删一个对象(历史在 git)")
def delete(layer: str, path: str, reason: str = "", svc: CollectionsService = Depends(collections), c: Ctx = Depends(ctx)):
    svc.delete(layer, path, reason, c)
    return ok()
