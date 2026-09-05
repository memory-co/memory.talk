"""/api/issues —— 讨论页:问题、立场、论证、manager、边、派活、写卡、历史、检索。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from models.card import Revision, SearchHit
from models.issue import (ArgumentCreate, IssueCreate, IssueSummary, IssueView, LinkCreate,
                          ManagerBind, PositionCreate, SpawnTask, WriteCard)
from services.issue import IssueService

router = APIRouter(prefix="/api/issues", tags=["issues"])


def issues(request: Request) -> IssueService:
    return request.app.state.issues


@router.get("", response_model=list[IssueSummary],
            summary="issue 清单(标注时「指认既有问题」查的就是它)")
def list_issues(manager_task: str | None = Query(None, description="只看这个 task 管的"),
                unmanaged: bool = Query(False, description="只看还没人管的"),
                svc: IssueService = Depends(issues)):
    return svc.list(manager_task, unmanaged)


@router.get("/search", response_model=list[SearchHit], summary="git grep 问题 / 立场 / 论证")
def search(q: str, svc: IssueService = Depends(issues)):
    return svc.search(q)


@router.post("", response_model=IssueView, status_code=201, summary="提一个问题(一个 commit)")
def create(req: IssueCreate, svc: IssueService = Depends(issues)):
    return svc.create(req)


@router.get("/{issue_id}", response_model=IssueView,
            summary="读一个 issue:立场按现算 credence 排序")
def get(issue_id: str, svc: IssueService = Depends(issues)):
    return svc.get(issue_id)


@router.get("/{issue_id}/history", response_model=list[Revision], summary="这个 issue 的 git log(辩论序列)")
def history(issue_id: str, svc: IssueService = Depends(issues)):
    return svc.history(issue_id)


@router.post("/{issue_id}/positions", response_model=IssueView, status_code=201,
             summary="加一个立场(只增不改)")
def add_position(issue_id: str, req: PositionCreate, svc: IssueService = Depends(issues)):
    return svc.add_position(issue_id, req)


@router.post("/{issue_id}/positions/{position_id}/arguments", response_model=IssueView,
             status_code=201, summary="对某个立场表态:+1 / 0 / -1,带证据")
def add_argument(issue_id: str, position_id: str, req: ArgumentCreate,
                 svc: IssueService = Depends(issues)):
    return svc.add_argument(issue_id, position_id, req)


@router.post("/{issue_id}/positions/{position_id}/tasks", response_model=IssueView,
             status_code=201, summary="为验证这个立场派出一个 task(先只记 id)")
def spawn_task(issue_id: str, position_id: str, req: SpawnTask,
               svc: IssueService = Depends(issues)):
    return svc.spawn_task(issue_id, position_id, req)


@router.put("/{issue_id}/manager", response_model=IssueView, summary="绑 / 换 / 解绑 manager task")
def bind_manager(issue_id: str, req: ManagerBind, svc: IssueService = Depends(issues)):
    return svc.bind_manager(issue_id, req)


@router.post("/{issue_id}/links", response_model=IssueView, status_code=201,
             summary="issue 之间连一条 IBIS 边")
def add_link(issue_id: str, req: LinkCreate, svc: IssueService = Depends(issues)):
    return svc.add_link(issue_id, req)


@router.post("/{issue_id}/card", response_model=IssueView, status_code=201,
             summary="争出结果:把某个立场写成一张卡(issue + card 同一个 commit)")
def write_card(issue_id: str, req: WriteCard, svc: IssueService = Depends(issues)):
    view, _ = svc.write_card(issue_id, req)
    return view
