"""/api/works —— 树、画布、会话(attach = 经 server 建现场)、痕迹、事件、召回。"""
from __future__ import annotations

from memorytalk.backend.models.result import Result, ok
from fastapi import APIRouter, Depends, Query, Request

from memorytalk.backend.models.collections import InboxItem
from memorytalk.backend.models.work_server import WorkServerInfo
from memorytalk.backend.models.work import (Canvas, CanvasPut, Event, Round, Session, SessionCreate, SessionView, Work,
                         WorkCreate, WorkNode, WorkUpdate, WorkUsers)
from memorytalk.backend.services.collections import CollectionsService
from memorytalk.backend.services.work import WorkService

router = APIRouter(prefix="/api/works", tags=["works"])


def works(request: Request) -> WorkService:
    return request.app.state.works


def collections(request: Request) -> CollectionsService:
    return request.app.state.collections


def user(request: Request) -> str | None:
    """谁在操作:门(中间件)解析 token 放进 request.state 的名字(身份,不是权限)。"""
    return request.state.user


@router.get("", response_model=Result[list[WorkNode]], summary="work 树(森林;root= 只看一棵;created_by= 只看某人建的)")
def forest(root: str | None = None, created_by: str | None = None, svc: WorkService = Depends(works)):
    return ok(svc.forest(root, created_by))


@router.get("/servers", response_model=Result[list[WorkServerInfo]],
            summary="有哪些 work server(bash / claude / codex / kimi / http / default)及各自响应的协议;attach 时按协议去找它们")
def servers(request: Request):
    return ok(request.app.state.work_servers.list())


@router.post("", response_model=Result[Work], status_code=201, summary="开工:建一个 work(parent= 挂到树上)")
def create(req: WorkCreate, svc: WorkService = Depends(works), who: str | None = Depends(user)):
    return ok(svc.create(req, created_by=who))


@router.get("/{work_id}", response_model=Result[Work], summary="读一个 work(带身份 = 打开它,记一笔在操作)")
def get(work_id: str, svc: WorkService = Depends(works), who: str | None = Depends(user)):
    svc.touch(work_id, who)
    return ok(svc.get(work_id))


@router.patch("/{work_id}", response_model=Result[Work],
              summary="改目标 / 状态;done 要求子 work 全完;结束后会话冻结")
def update(work_id: str, req: WorkUpdate, svc: WorkService = Depends(works), who: str | None = Depends(user)):
    svc.touch(work_id, who)
    return ok(svc.update(work_id, req))


@router.get("/{work_id}/events", response_model=Result[list[Event]], summary="work 自己的时间线")
def events(work_id: str, svc: WorkService = Depends(works)):
    return ok(svc.history(work_id))


@router.get("/{work_id}/inbox", response_model=Result[list[InboxItem]],
            summary="收件箱:被 manager.json 路由过来的变动(Collections 的对象、子 work 的状态)")
def inbox(work_id: str, svc: WorkService = Depends(works)):
    return ok(svc.read_inbox(work_id))


@router.get("/{work_id}/manager", summary="这个 work 的变动打给谁:manager.json,没有则父 work", response_model=Result[dict])
def get_manager(work_id: str, svc: WorkService = Depends(works)) -> dict:
    return ok({"work": svc.manager_of(work_id)})


@router.put("/{work_id}/manager", summary="改写默认:这棵子树的变动打给指定 work(null = 删掉,回到父)", response_model=Result[dict])
def put_manager(work_id: str, req: dict, svc: WorkService = Depends(works)) -> dict:
    return ok({"work": svc.set_manager(work_id, req.get("work"))})


@router.get("/{work_id}/users", response_model=Result[WorkUsers],
            summary="user:谁当前正在操作(current)、谁历史操作过(history)。只做可见性,不做权限")
def users(work_id: str, svc: WorkService = Depends(works)):
    return ok(svc.list_users(work_id))


@router.post("/{work_id}/users/touch", response_model=Result[WorkUsers], summary="我在操作这个 work(心跳;身份来自登录态)")
def touch(work_id: str, svc: WorkService = Depends(works), who: str | None = Depends(user)):
    svc.touch(work_id, who)
    return ok(svc.list_users(work_id))


@router.get("/{work_id}/canvas", response_model=Result[Canvas], summary="画布(视图,随时可重排)")
def get_canvas(work_id: str, svc: WorkService = Depends(works)):
    return ok(svc.get_canvas(work_id))


@router.put("/{work_id}/canvas", response_model=Result[Canvas], summary="全量写画布(version 乐观锁)")
def put_canvas(work_id: str, req: CanvasPut, svc: WorkService = Depends(works), who: str | None = Depends(user)):
    svc.touch(work_id, who)
    return ok(svc.put_canvas(work_id, req))


@router.get("/{work_id}/sessions", response_model=Result[list[SessionView]], summary="会话清单(含活没活着)")
def sessions(work_id: str, svc: WorkService = Depends(works)):
    return ok(svc.list_sessions(work_id))


@router.post("/{work_id}/sessions", response_model=Result[SessionView], status_code=201,
             summary="在 work 里打开一个块:协议 → server 建现场,登记会话,交回窗 + 把手")
def attach(work_id: str, req: SessionCreate, svc: WorkService = Depends(works), who: str | None = Depends(user)):
    svc.touch(work_id, who)
    return ok(svc.attach(work_id, req.uri))


@router.post("/{work_id}/sessions/{session_id}/attach", response_model=Result[SessionView],
             summary="重入:幂等取回同一个现场")
def reattach(work_id: str, session_id: str, svc: WorkService = Depends(works), who: str | None = Depends(user)):
    svc.touch(work_id, who)
    return ok(svc.reattach(work_id, session_id))


@router.delete("/{work_id}/sessions/{session_id}", summary="关闭即回收:销毁现场 + 删登记")
def detach(work_id: str, session_id: str, svc: WorkService = Depends(works), who: str | None = Depends(user)):
    svc.touch(work_id, who)
    svc.detach(work_id, session_id)
    return ok()


@router.get("/{work_id}/sessions/{session_id}/capture",
            summary="观测:抓终端屏幕(把手 capture)")
def capture(work_id: str, session_id: str, lines: int = Query(200, ge=1, le=5000),
            svc: WorkService = Depends(works)):
    return ok(svc.capture(work_id, session_id, lines))


@router.get("/{work_id}/sessions/{session_id}/rounds", response_model=Result[list[Round]],
            summary="痕迹:agent 会话的 round(先从把手同步新 round,再读 rounds.jsonl)")
def rounds(work_id: str, session_id: str, svc: WorkService = Depends(works)):
    return ok(svc.rounds(work_id, session_id))
