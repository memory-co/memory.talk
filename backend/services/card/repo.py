"""card 的文件形态:markdown + 简单 frontmatter。不引 yaml,frontmatter 只有 key: value 行。"""
from __future__ import annotations

import re
from pathlib import Path

from models.card import Card
from services.store import MemoryLayout, atomic_write, read_text

_FM = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.S)


def parse(card_id: str, text: str) -> Card:
    m = _FM.match(text)
    meta: dict[str, str] = {}
    body = text
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        body = m.group(2)
    links = [s.strip() for s in meta.get("links", "").split(",") if s.strip()]
    return Card(
        id=card_id,
        title=meta.get("title") or card_id.rsplit("/", 1)[-1],
        body=body.strip("\n"),
        context=meta.get("context", ""),
        links=links,
        issue=meta.get("issue") or None,
        status=meta.get("status", "active"),  # type: ignore[arg-type]
    )


def serialize(card: Card) -> str:
    lines = ["---", f"title: {card.title}"]
    if card.context:
        lines.append(f"context: {card.context}")
    if card.links:
        lines.append("links: " + ", ".join(card.links))
    if card.issue:
        lines.append(f"issue: {card.issue}")
    if card.status != "active":
        lines.append(f"status: {card.status}")
    lines.append("---")
    return "\n".join(lines) + "\n\n" + card.body.rstrip("\n") + "\n"


_SLUG_BAD = re.compile(r"[\s/\\:*?\"<>|#]+")


def slugify(title: str) -> str:
    s = _SLUG_BAD.sub("-", title.strip()).strip("-")
    return s or "untitled"


def make_id(dir_: str, slug: str) -> str:
    dir_ = dir_.strip("/")
    return f"{dir_}/{slug}" if dir_ else slug


class CardRepo:
    def __init__(self, layout: MemoryLayout) -> None:
        self.layout = layout

    def path(self, card_id: str) -> Path:
        return self.layout.card_path(card_id)

    def rel(self, card_id: str) -> str:
        return self.layout.rel(self.path(card_id))

    def exists(self, card_id: str) -> bool:
        return self.path(card_id).is_file()

    def load(self, card_id: str) -> Card | None:
        text = read_text(self.path(card_id))
        return None if text is None else parse(card_id, text)

    def save(self, card: Card) -> str:
        atomic_write(self.path(card.id), serialize(card))
        return self.rel(card.id)

    def walk(self) -> list[Card]:
        root = self.layout.cards
        if not root.is_dir():
            return []
        cards = []
        for p in sorted(root.rglob("*.md")):
            cid = p.relative_to(root).with_suffix("").as_posix()
            text = read_text(p)
            if text is not None:
                cards.append(parse(cid, text))
        return cards
