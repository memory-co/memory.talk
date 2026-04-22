"""Filesystem layout for sessions/, cards/, links/ — the source of truth."""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Iterator


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


# ---------- sessions ----------

def session_dir(sessions_root: Path, source: str, session_id: str) -> Path:
    raw = session_id[len("sess_"):] if session_id.startswith("sess_") else session_id
    bucket = (raw[:2] if len(raw) >= 2 else raw).lower()
    return sessions_root / source / bucket / session_id


def write_session_meta(sessions_root: Path, source: str, session_id: str, meta: dict) -> None:
    d = session_dir(sessions_root, source, session_id)
    _atomic_write(d / "meta.json", json.dumps(meta, ensure_ascii=False, indent=2))


def read_session_meta(sessions_root: Path, source: str, session_id: str) -> dict | None:
    p = session_dir(sessions_root, source, session_id) / "meta.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def append_session_rounds(sessions_root: Path, source: str, session_id: str, rounds: list[dict]) -> None:
    d = session_dir(sessions_root, source, session_id)
    d.mkdir(parents=True, exist_ok=True)
    p = d / "rounds.jsonl"
    with p.open("a", encoding="utf-8") as f:
        for r in rounds:
            f.write(json.dumps(r, ensure_ascii=False))
            f.write("\n")


def read_session_rounds(sessions_root: Path, source: str, session_id: str) -> list[dict]:
    p = session_dir(sessions_root, source, session_id) / "rounds.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def iter_session_dirs(sessions_root: Path) -> Iterator[Path]:
    if not sessions_root.exists():
        return
    for src_dir in sorted(p for p in sessions_root.iterdir() if p.is_dir()):
        for bucket in sorted(p for p in src_dir.iterdir() if p.is_dir()):
            for sess in sorted(p for p in bucket.iterdir() if p.is_dir()):
                yield sess


# ---------- cards ----------

def card_path(cards_root: Path, card_id: str) -> Path:
    raw = card_id[len("card_"):] if card_id.startswith("card_") else card_id
    bucket = (raw[:2] if len(raw) >= 2 else raw).lower()
    return cards_root / bucket / f"{card_id}.json"


def write_card(cards_root: Path, card: dict) -> None:
    p = card_path(cards_root, card["card_id"])
    _atomic_write(p, json.dumps(card, ensure_ascii=False, indent=2))


def read_card(cards_root: Path, card_id: str) -> dict | None:
    p = card_path(cards_root, card_id)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def iter_cards(cards_root: Path) -> Iterator[dict]:
    if not cards_root.exists():
        return
    for bucket in sorted(p for p in cards_root.iterdir() if p.is_dir()):
        for f in sorted(bucket.glob("*.json")):
            yield json.loads(f.read_text(encoding="utf-8"))


# ---------- links ----------

def link_path(links_root: Path, link_id: str) -> Path:
    raw = link_id[len("link_"):] if link_id.startswith("link_") else link_id
    bucket = (raw[:2] if len(raw) >= 2 else raw).lower()
    return links_root / bucket / f"{link_id}.json"


def write_link(links_root: Path, link: dict) -> None:
    p = link_path(links_root, link["link_id"])
    _atomic_write(p, json.dumps(link, ensure_ascii=False, indent=2))


def read_link(links_root: Path, link_id: str) -> dict | None:
    p = link_path(links_root, link_id)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def iter_links(links_root: Path) -> Iterator[dict]:
    if not links_root.exists():
        return
    for bucket in sorted(p for p in links_root.iterdir() if p.is_dir()):
        for f in sorted(bucket.glob("*.json")):
            yield json.loads(f.read_text(encoding="utf-8"))
