"""IssueService:问题、立场、论证、manager、派活、写卡(docs/works/v5/issue.md)。每个动作一个 commit。"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from models.card import Card, Origin, Revision, SearchHit
from models.issue import (Argument, ArgumentCreate, Issue, IssueCreate, IssueLink, IssueSummary,
                          IssueView, LinkCreate, ManagerBind, OpenDiscussion, Position,
                          PositionCreate, PositionView, SpawnTask, WriteCard)
from services.card import CardExists, CardService, make_id, slugify
from services.store import StoreService

from .links import add_link
from .manager import bind_manager, spawn_task
from .repo import IssueRepo


class IssueNotFound(LookupError):
    pass


class PositionNotFound(LookupError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _new_id() -> str:
    return "iss_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + secrets.token_hex(2)


def _trailer(reason: str, origin: Origin | None = None) -> str:
    parts = []
    if reason:
        parts.append(f"Reason: {reason}")
    if origin:
        rounds = ",".join(map(str, origin.rounds)) if origin.rounds else "-"
        parts.append(f"Task: {origin.task_id}\nRounds: {rounds}")
    return "\n".join(parts)


def _view(issue: Issue) -> IssueView:
    positions = []
    for p in issue.positions:
        up = sum(1 for a in p.arguments if a.stance == 1)
        down = sum(1 for a in p.arguments if a.stance == -1)
        neutral = sum(1 for a in p.arguments if a.stance == 0)
        positions.append(PositionView(**p.model_dump(), up=up, down=down, neutral=neutral,
                                      credence=up - down))
    positions.sort(key=lambda p: p.credence, reverse=True)
    return IssueView(**issue.model_dump(exclude={"positions"}), positions=positions)


class IssueService:
    def __init__(self, store: StoreService, cards: CardService) -> None:
        self.store = store
        self.cards = cards
        self.repo = IssueRepo(store.memory.layout)
        self.git = store.memory.git

    # ---- 读 ----

    def _load(self, issue_id: str) -> Issue:
        issue = self.repo.load(issue_id)
        if issue is None:
            raise IssueNotFound(issue_id)
        return issue

    def get(self, issue_id: str) -> IssueView:
        return _view(self._load(issue_id))

    def list(self, manager_task: str | None = None, unmanaged: bool = False) -> list[IssueSummary]:
        out = []
        for i in self.repo.walk():
            if manager_task and i.manager_task != manager_task:
                continue
            if unmanaged and i.manager_task:
                continue
            out.append(IssueSummary(id=i.id, question=i.question, manager_task=i.manager_task,
                                    card=i.card, position_count=len(i.positions)))
        return out

    def history(self, issue_id: str) -> list[Revision]:
        self._load(issue_id)
        return [Revision(sha=c.sha, author=c.author, date=c.date, subject=c.subject, body=c.body)
                for c in self.git.log(self.repo.rel(issue_id))]

    def search(self, query: str) -> list[SearchHit]:
        return [SearchHit(kind="issue", id=h.path[len("issues/"):].removesuffix(".json"),
                          path=h.path, line=h.line, text=h.text)
                for h in self.git.grep(query, "issues/")]

    # ---- 写 ----

    def create(self, req: IssueCreate) -> IssueView:
        issue = Issue(id=_new_id(), question=req.question, origin=req.origin,
                      manager_task=req.manager_task, created_at=_now())
        rel = self.repo.save(issue)
        self.git.commit([rel], f"issue: raise {issue.id}: {issue.question[:60]}",
                        _trailer(req.reason, req.origin))
        return _view(issue)

    def add_position(self, issue_id: str, req: PositionCreate) -> IssueView:
        issue = self._load(issue_id)
        pos = Position(id=f"p{len(issue.positions) + 1}", claim=req.claim, origin=req.origin,
                       created_at=_now())
        issue.positions.append(pos)
        rel = self.repo.save(issue)
        self.git.commit([rel], f"issue: position {issue_id}#{pos.id}: {pos.claim[:60]}",
                        _trailer(req.reason, req.origin))
        return _view(issue)

    def _position(self, issue: Issue, position_id: str) -> Position:
        for p in issue.positions:
            if p.id == position_id:
                return p
        raise PositionNotFound(f"{issue.id}#{position_id}")

    def add_argument(self, issue_id: str, position_id: str, req: ArgumentCreate) -> IssueView:
        issue = self._load(issue_id)
        pos = self._position(issue, position_id)
        arg = Argument(id=f"a{len(pos.arguments) + 1}", stance=req.stance, comment=req.comment,
                       evidence=req.evidence, task_id=req.task_id, created_at=_now())
        pos.arguments.append(arg)
        rel = self.repo.save(issue)
        sign = {1: "+1", 0: "0", -1: "-1"}[req.stance]
        self.git.commit([rel], f"issue: argue {issue_id}#{position_id} {sign}",
                        _trailer(req.reason, req.evidence))
        return _view(issue)

    def bind_manager(self, issue_id: str, req: ManagerBind) -> IssueView:
        issue = self._load(issue_id)
        bind_manager(issue, req.task_id)
        rel = self.repo.save(issue)
        verb = f"manage {issue_id} by {req.task_id}" if req.task_id else f"unmanage {issue_id}"
        self.git.commit([rel], f"issue: {verb}", _trailer(req.reason))
        return _view(issue)

    def add_link(self, issue_id: str, req: LinkCreate) -> IssueView:
        issue = self._load(issue_id)
        if add_link(issue, IssueLink(type=req.type, target=req.target)):
            rel = self.repo.save(issue)
            self.git.commit([rel], f"issue: link {issue_id} {req.type} {req.target}",
                            _trailer(req.reason))
        return _view(issue)

    def spawn_task(self, issue_id: str, position_id: str, req: SpawnTask) -> IssueView:
        issue = self._load(issue_id)
        pos = self._position(issue, position_id)
        if spawn_task(pos, req.task_id):
            rel = self.repo.save(issue)
            self.git.commit([rel], f"issue: spawn {issue_id}#{position_id} -> {req.task_id}",
                            _trailer(req.reason))
        return _view(issue)

    # ---- 跨对象的决定:同一个 commit ----

    def write_card(self, issue_id: str, req: WriteCard) -> tuple[IssueView, Card]:
        """争出结果:issue 记结论(card 字段)+ 建卡,一个 commit。"""
        issue = self._load(issue_id)
        pos = self._position(issue, req.position_id)
        cid = make_id(req.dir, req.slug or slugify(req.title))
        if self.cards.repo.exists(cid):
            raise CardExists(cid)
        card = Card(id=cid, title=req.title, body=req.body or pos.claim, context=req.context,
                    issue=issue.id)
        issue.card = cid
        rels = [self.repo.save(issue), self.cards.write_no_commit(card)]
        self.git.commit(rels, f"decide: {issue_id}#{pos.id} -> card {cid}",
                        _trailer(req.reason, pos.origin))
        return _view(issue), card

    def open_discussion(self, card_id: str, req: OpenDiscussion) -> tuple[IssueView, Card]:
        """对一张卡不同意:开 issue 挂到卡上当讨论页,一个 commit。"""
        card = self.cards.get(card_id)
        issue = Issue(id=_new_id(), question=req.question, origin=req.origin,
                      manager_task=req.manager_task, card=card_id, created_at=_now())
        card = card.model_copy(update={"issue": issue.id})
        rels = [self.repo.save(issue), self.cards.write_no_commit(card)]
        self.git.commit(rels, f"discuss: card {card_id} -> {issue.id}: {issue.question[:60]}",
                        _trailer(req.reason, req.origin))
        return _view(issue), card


__all__ = ["IssueService", "IssueNotFound", "PositionNotFound"]
