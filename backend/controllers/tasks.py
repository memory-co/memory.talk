"""/api/tasks —— 树、画布、会话(attach = 经 server 建现场)、痕迹、事件、召回。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import PlainTextResponse

from models.task import (Canvas, CanvasPut, Event, Members, Round, Session, SessionCreate, SessionView,
                         Task, TaskCreate, TaskNode, TaskUpdate)
from services.card import CardService
from services.task import TaskService

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def tasks(request: Request) -> TaskService:
    return request.app.state.tasks


def cards(request: Request) -> CardService:
    return request.app.state.cards


def user(x_memory_talk_user: str | None = Header(None, alias="X-Memory-Talk-User")) -> str | None:
    """谁在操作:客户端自报,不校验(整个实例给一个团队用,不做权限)。"""
    return x_memory_talk_user


@router.get("", response_model=list[TaskNode], summary="task 树(森林;root= 只看一棵)")
def forest(root: str | None = None, svc: TaskService = Depends(tasks)):
    return svc.forest(root)


@router.post("", response_model=Task, status_code=201, summary="开工:建一个 task(parent= 挂到树上)")
def create(req: TaskCreate, svc: TaskService = Depends(tasks), who: str | None = Depends(user)):
    t = svc.create(req)
    svc.touch(t.id, who)
    return t


@router.get("/{task_id}", response_model=Task, summary="读一个 task(带身份 = 打开它,记一笔在操作)")
def get(task_id: str, svc: TaskService = Depends(tasks), who: str | None = Depends(user)):
    svc.touch(task_id, who)
    return svc.get(task_id)


@router.patch("/{task_id}", response_model=Task,
              summary="改目标 / 项目 / 状态;done 要求子 task 全完;结束后会话冻结")
def update(task_id: str, req: TaskUpdate, svc: TaskService = Depends(tasks), who: str | None = Depends(user)):
    svc.touch(task_id, who)
    return svc.update(task_id, req)


@router.get("/{task_id}/events", response_model=list[Event], summary="task 自己的时间线")
def events(task_id: str, svc: TaskService = Depends(tasks)):
    return svc.history(task_id)


@router.get("/{task_id}/recall", response_class=PlainTextResponse,
            summary="开工注入:card 目录文本(card → task 的接口)")
def recall(task_id: str, dir: str = "", svc: TaskService = Depends(tasks), c: CardService = Depends(cards)):
    svc.get(task_id)
    return c.recall_text(dir)


@router.get("/{task_id}/members", response_model=Members,
            summary="成员(人):谁当前正在操作(current)、谁历史操作过(history)。只做可见性,不做权限")
def members(task_id: str, svc: TaskService = Depends(tasks)):
    return svc.list_members(task_id)


@router.post("/{task_id}/members/touch", response_model=Members, summary="我在操作这个 task(心跳;身份来自 X-Memory-Talk-User)")
def touch(task_id: str, svc: TaskService = Depends(tasks), who: str | None = Depends(user)):
    svc.touch(task_id, who)
    return svc.list_members(task_id)


@router.get("/{task_id}/canvas", response_model=Canvas, summary="画布(视图,随时可重排)")
def get_canvas(task_id: str, svc: TaskService = Depends(tasks)):
    return svc.get_canvas(task_id)


@router.put("/{task_id}/canvas", response_model=Canvas, summary="全量写画布(version 乐观锁)")
def put_canvas(task_id: str, req: CanvasPut, svc: TaskService = Depends(tasks), who: str | None = Depends(user)):
    svc.touch(task_id, who)
    return svc.put_canvas(task_id, req)


@router.get("/{task_id}/sessions", response_model=list[SessionView], summary="会话清单(含活没活着)")
def sessions(task_id: str, svc: TaskService = Depends(tasks)):
    return svc.list_sessions(task_id)


@router.post("/{task_id}/sessions", response_model=SessionView, status_code=201,
             summary="在 task 里打开一个块:协议 → server 建现场,登记会话,交回窗 + 把手")
def attach(task_id: str, req: SessionCreate, svc: TaskService = Depends(tasks), who: str | None = Depends(user)):
    svc.touch(task_id, who)
    return svc.attach(task_id, req.uri)


@router.post("/{task_id}/sessions/{session_id}/attach", response_model=SessionView,
             summary="重入:幂等取回同一个现场")
def reattach(task_id: str, session_id: str, svc: TaskService = Depends(tasks), who: str | None = Depends(user)):
    svc.touch(task_id, who)
    return svc.reattach(task_id, session_id)


@router.delete("/{task_id}/sessions/{session_id}", status_code=204, summary="关闭即回收:销毁现场 + 删登记")
def detach(task_id: str, session_id: str, svc: TaskService = Depends(tasks), who: str | None = Depends(user)):
    svc.touch(task_id, who)
    svc.detach(task_id, session_id)


@router.get("/{task_id}/sessions/{session_id}/capture", response_class=PlainTextResponse,
            summary="观测:抓终端屏幕(把手 capture)")
def capture(task_id: str, session_id: str, lines: int = Query(200, ge=1, le=5000),
            svc: TaskService = Depends(tasks)):
    return svc.capture(task_id, session_id, lines)


@router.get("/{task_id}/sessions/{session_id}/rounds", response_model=list[Round],
            summary="痕迹:agent 会话的 round(先从把手同步新 round,再读 rounds.jsonl)")
def rounds(task_id: str, session_id: str, svc: TaskService = Depends(tasks)):
    return svc.rounds(task_id, session_id)
