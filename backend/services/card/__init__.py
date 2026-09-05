"""CardService:词条的读写、目录、历史、检索(docs/works/v5/card.md)。改卡 = commit。"""
from __future__ import annotations

from models.card import (Card, CardCreate, CardUpdate, CatalogDir, Origin, Revision,
                         SearchHit)
from services.store import StoreService

from .catalog import build_catalog
from .recall import render_catalog
from .repo import CardRepo, make_id, slugify


class CardNotFound(LookupError):
    pass


class CardExists(ValueError):
    pass


def _trailer(reason: str, origin: Origin | None) -> str:
    parts = []
    if reason:
        parts.append(f"Reason: {reason}")
    if origin:
        rounds = ",".join(map(str, origin.rounds)) if origin.rounds else "-"
        parts.append(f"Task: {origin.task_id}\nRounds: {rounds}")
    return "\n".join(parts)


class CardService:
    def __init__(self, store: StoreService) -> None:
        self.store = store
        self.repo = CardRepo(store.memory.layout)
        self.git = store.memory.git

    # ---- 读 ----

    def get(self, card_id: str) -> Card:
        card = self.repo.load(card_id)
        if card is None:
            raise CardNotFound(card_id)
        return card

    def catalog(self, root: str = "", include_deprecated: bool = False) -> CatalogDir:
        return build_catalog(self.repo.walk(), root, include_deprecated)

    def recall_text(self, root: str = "") -> str:
        return render_catalog(self.catalog(root))

    def history(self, card_id: str) -> list[Revision]:
        self.get(card_id)
        return [Revision(sha=c.sha, author=c.author, date=c.date, subject=c.subject, body=c.body)
                for c in self.git.log(self.repo.rel(card_id))]

    def at_revision(self, card_id: str, sha: str) -> Card:
        from .repo import parse
        text = self.git.show(sha, self.repo.rel(card_id))
        if text is None:
            raise CardNotFound(f"{card_id}@{sha}")
        return parse(card_id, text)

    def search(self, query: str) -> list[SearchHit]:
        hits = []
        for h in self.git.grep(query, "cards/"):
            cid = h.path[len("cards/"):].removesuffix(".md")
            hits.append(SearchHit(kind="card", id=cid, path=h.path, line=h.line, text=h.text))
        return hits

    # ---- 写(每个动作一个 commit)----

    def create(self, req: CardCreate) -> Card:
        cid = make_id(req.dir, req.slug or slugify(req.title))
        if self.repo.exists(cid):
            raise CardExists(cid)
        card = Card(id=cid, title=req.title, body=req.body, context=req.context, links=req.links)
        rel = self.repo.save(card)
        self.git.commit([rel], f"card: write {cid}", _trailer(req.reason, req.origin))
        return card

    def update(self, card_id: str, req: CardUpdate) -> Card:
        card = self.get(card_id)
        data = card.model_dump()
        for k in ("title", "body", "context", "links"):
            v = getattr(req, k)
            if v is not None:
                data[k] = v
        card = Card(**data)
        rel = self.repo.save(card)
        self.git.commit([rel], f"card: edit {card_id}", _trailer(req.reason, req.origin))
        return card

    def deprecate(self, card_id: str, reason: str = "") -> Card:
        card = self.get(card_id)
        card = card.model_copy(update={"status": "deprecated"})
        rel = self.repo.save(card)
        self.git.commit([rel], f"card: deprecate {card_id}", _trailer(reason, None))
        return card

    # ---- 供 issue service 在同一个 commit 里用(不自己提交)----

    def write_no_commit(self, card: Card) -> str:
        return self.repo.save(card)


__all__ = ["CardService", "CardNotFound", "CardExists", "make_id", "slugify"]
