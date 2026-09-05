"""/api/cards —— 词条:目录、读、写、改、废弃、历史、检索、开讨论页。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse

from models.card import Card, CardCreate, CardUpdate, CatalogDir, Revision, SearchHit
from models.issue import IssueView, OpenDiscussion
from services.card import CardService
from services.issue import IssueService

router = APIRouter(prefix="/api/cards", tags=["cards"])


def cards(request: Request) -> CardService:
    return request.app.state.cards


def issues(request: Request) -> IssueService:
    return request.app.state.issues


@router.get("", response_model=CatalogDir, summary="目录(按目录分层的标题清单;召回注入的就是它)")
def catalog(dir: str = Query("", description="只看这个目录之下"),
            include_deprecated: bool = False, svc: CardService = Depends(cards)):
    return svc.catalog(dir, include_deprecated)


@router.get("/recall", summary="目录渲染成可直接注入 agent 上下文的文本",
            response_class=PlainTextResponse)
def recall(dir: str = "", svc: CardService = Depends(cards)):
    return svc.recall_text(dir)


@router.get("/search", response_model=list[SearchHit], summary="git grep 词条正文")
def search(q: str, svc: CardService = Depends(cards)):
    return svc.search(q)


@router.post("", response_model=Card, status_code=201, summary="写一张卡(一个 commit)")
def create(req: CardCreate, svc: CardService = Depends(cards)):
    return svc.create(req)


@router.get("/{card_id:path}/history", response_model=list[Revision], summary="这张卡的 git log")
def history(card_id: str, svc: CardService = Depends(cards)):
    return svc.history(card_id)


@router.post("/{card_id:path}/issue", response_model=IssueView, status_code=201,
             summary="对这张卡不同意:开一个 issue 挂上去当讨论页(一个 commit)")
def open_discussion(card_id: str, req: OpenDiscussion, svc: IssueService = Depends(issues)):
    view, _ = svc.open_discussion(card_id, req)
    return view


@router.get("/{card_id:path}", response_model=Card, summary="读一张卡(可指定历史版本)")
def get(card_id: str, rev: str | None = Query(None, description="git sha;缺省读当前"),
        svc: CardService = Depends(cards)):
    return svc.at_revision(card_id, rev) if rev else svc.get(card_id)


@router.put("/{card_id:path}", response_model=Card, summary="改一张卡(一个 commit,旧内容进历史)")
def update(card_id: str, req: CardUpdate, svc: CardService = Depends(cards)):
    return svc.update(card_id, req)


@router.delete("/{card_id:path}", response_model=Card, summary="废弃一张卡(文件留着,标 deprecated)")
def deprecate(card_id: str, reason: str = "", svc: CardService = Depends(cards)):
    return svc.deprecate(card_id, reason)
