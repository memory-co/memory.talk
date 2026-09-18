"""/api/collections —— 认知层:层、树、检索、对象(目录里的一组文件)CRUD、历史。"""
from __future__ import annotations

from memorytalk.backend.models.result import Result, ok
from fastapi import APIRouter, Depends, Header, Query, Request

from memorytalk.backend.models.collections import (CheckResult, LayerInfo, Manager, ManagerPut, Obj, ObjWrite, RecentPage, Revision,
                                                     SearchHit, TreeItem, TreeView)
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

@router.get("/layers", response_model=Result[list[LayerInfo]], summary="有哪些层(最底在前)及各自的协议;用户层来自 <home>/layers/*.yaml")
def layers(svc: CollectionsService = Depends(collections)):
    return ok(svc.layer_infos())


@router.get("/config", summary="collections.json 本体 + 它的 git 历史(层的变化史)", response_model=Result[dict])
def config(svc: CollectionsService = Depends(collections)) -> dict:
    return ok({"config": svc.anchor(), "history": [r.model_dump() for r in svc.anchor_history()]})


@router.get("/tree", response_model=Result[TreeView],
            summary="浏览目录:有什么(items:对象折成一项、目录、origin 文件;layer= 只留一层,recursive=1 拍平到底)+ 还能建什么(can_create)+ 这个名字行不行(candidate=)")
def tree(path: str = "", candidate: str | None = None, layer: str | None = None, recursive: bool = False, svc: CollectionsService = Depends(collections)):
    return ok(svc.tree(path, candidate, layer, recursive))


@router.get("/recent", response_model=Result[RecentPage],
            summary="最近改过的对象:沿 stack 时间线往回,文件折回对象,每个对象只出现一次;layer= / path= 过滤,before=<sha> 翻页,next 是下一页游标")
def recent(layer: str | None = None, path: str = "", limit: int = Query(20, ge=1, le=200), before: str | None = None,
           svc: CollectionsService = Depends(collections)):
    return ok(svc.recent(layer, path, limit, before))


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


# ---- 对象 ----

def _files(svc: CollectionsService, layer: str, req: ObjWrite) -> dict:
    """请求体 → 目录里的文件改动:origin 用 content,其余用 files。"""
    if svc.layer(layer).suffix is None:
        if req.content is None:
            raise CollectionsError("invalid", "origin 要给 content", 400)
        return {"": req.content}
    if not req.files:
        raise CollectionsError("invalid", "要给 files:目录里的文件 {相对路径: 内容}", 400)
    return dict(req.files)


def _dry(fn) -> CheckResult:
    try:
        fn()
        return CheckResult(ok=True)
    except CollectionsError as e:
        return CheckResult(ok=False, reason=str(e))


@router.post("/{layer}/{path:path}", response_model=Result[Obj | CheckResult], status_code=201,
             summary="建一个对象:目录里的文件(files);origin 用 content。整批按层的协议校验,过了一个 [layer] 提交;dry_run=1 只校验")
def create(layer: str, path: str, req: ObjWrite, dry_run: bool = False, svc: CollectionsService = Depends(collections), c: Ctx = Depends(ctx)):
    if dry_run:
        return ok(_dry(lambda: svc.create(layer, path, _files(svc, layer, req), req.reason, c, req.subject, dry_run=True)))
    return ok(svc.create(layer, path, _files(svc, layer, req), req.reason, c, req.subject))


@router.get("/{layer}/{path:path}", response_model=Result[Obj], summary="读一个对象(rev= 读历史版本)")
def get(layer: str, path: str, rev: str | None = Query(None), svc: CollectionsService = Depends(collections)):
    return ok(svc.get(layer, path, rev))


@router.put("/{layer}/{path:path}", response_model=Result[Obj | CheckResult],
            summary="改一个对象:files 加 / 改 / 删(null)目录里的文件,没提到的不动,整批按层的协议校验;origin 整体替换;dry_run=1 只校验")
def update(layer: str, path: str, req: ObjWrite, dry_run: bool = False, svc: CollectionsService = Depends(collections), c: Ctx = Depends(ctx)):
    if dry_run:
        return ok(_dry(lambda: svc.update(layer, path, _files(svc, layer, req), req.reason, c, req.subject, dry_run=True)))
    return ok(svc.update(layer, path, _files(svc, layer, req), req.reason, c, req.subject))


@router.delete("/{layer}/{path:path}", summary="删一个对象(历史在 git)")
def delete(layer: str, path: str, reason: str = "", svc: CollectionsService = Depends(collections), c: Ctx = Depends(ctx)):
    svc.delete(layer, path, reason, c)
    return ok()
