"""Rebuild service — async reconstruct SQLite + LanceDB from file-layer truth."""
from __future__ import annotations
import json
import time

import aiofiles

from memory_talk_v2.config import Config
from memory_talk_v2.embedding import Embedder
from memory_talk_v2.storage import files as F
from memory_talk_v2.storage.lancedb import LanceStore
from memory_talk_v2.storage.sqlite import SQLiteStore


def _rounds_to_text(rounds: list[dict]) -> str:
    parts: list[str] = []
    for r in rounds:
        for b in r.get("content") or []:
            t = b.get("type")
            if t in ("text", "code"):
                parts.append(b.get("text") or "")
            elif t == "thinking":
                parts.append(b.get("thinking") or "")
    return "\n".join(p for p in parts if p)


def _card_emb_text(card: dict) -> str:
    rounds_text = "\n".join(r.get("text") or "" for r in (card.get("rounds") or []))
    summary = card.get("summary") or ""
    return f"{summary}\n{rounds_text}" if rounds_text else summary


class RebuildService:
    def __init__(
        self, *,
        config: Config,
        db: SQLiteStore,
        vectors: LanceStore,
        embedder: Embedder,
    ):
        self.config = config
        self.db = db
        self.vectors = vectors
        self.embedder = embedder

    async def rebuild(self) -> dict:
        errors_count = 0

        await self.db.clear_all()
        await self.vectors.drop_cards()
        await self.vectors.drop_sessions()

        sessions_count = 0
        for sess_dir in F.iter_session_dirs(self.config.sessions_dir):
            meta_path = sess_dir / "meta.json"
            rounds_path = sess_dir / "rounds.jsonl"
            if not meta_path.exists():
                continue
            try:
                async with aiofiles.open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.loads(await f.read())
            except json.JSONDecodeError:
                errors_count += 1
                continue
            session_id = meta.get("session_id") or sess_dir.name
            source = meta.get("source") or sess_dir.parent.parent.name
            rounds_from_file: list[dict] = []
            if rounds_path.exists():
                async with aiofiles.open(rounds_path, "r", encoding="utf-8") as f:
                    text = await f.read()
                for line in text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rounds_from_file.append(json.loads(line))
                    except json.JSONDecodeError:
                        errors_count += 1

            await self.db.upsert_session(
                session_id=session_id, source=source,
                created_at=meta.get("created_at") or "",
                synced_at=meta.get("synced_at") or "",
                metadata=meta.get("metadata") or {},
                tags=meta.get("tags") or [],
                round_count=meta.get("round_count") or len(rounds_from_file),
            )
            if rounds_from_file:
                await self.db.upsert_rounds(session_id, rounds_from_file)
                await self.vectors.add_session(session_id, _rounds_to_text(rounds_from_file))
            sessions_count += 1

        cards_count = 0
        async for card in F.iter_cards(self.config.cards_dir):
            try:
                await self.db.insert_card(
                    card_id=card["card_id"],
                    summary=card.get("summary") or "",
                    rounds=card.get("rounds") or [],
                    created_at=card.get("created_at") or "",
                    expires_at=card.get("expires_at") or "",
                )
            except Exception:
                errors_count += 1
                continue
            emb_text = _card_emb_text(card)
            vector = await self.embedder.embed_one(emb_text)
            await self.vectors.add_card(card["card_id"], emb_text, vector)
            cards_count += 1

        async for link in F.iter_links(self.config.links_dir):
            try:
                await self.db.insert_link(
                    link_id=link["link_id"],
                    source_id=link["source_id"], source_type=link["source_type"],
                    target_id=link["target_id"], target_type=link["target_type"],
                    comment=link.get("comment"),
                    expires_at=link.get("expires_at"),
                    created_at=link.get("created_at") or "",
                )
            except Exception:
                errors_count += 1

        searches_replayed = 0
        if self.config.search_log_dir.exists():
            for jsonl in sorted(self.config.search_log_dir.glob("*.jsonl")):
                async with aiofiles.open(jsonl, "r", encoding="utf-8") as f:
                    text = await f.read()
                for line in text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        await self.db.insert_search_log(
                            search_id=rec["search_id"], query=rec.get("query") or "",
                            where_dsl=rec.get("where"), top_k=int(rec.get("top_k") or 0),
                            created_at=rec.get("created_at") or "",
                            response_json=json.dumps(rec, ensure_ascii=False),
                        )
                        searches_replayed += 1
                    except Exception:
                        errors_count += 1

        await self.vectors.ensure_fts_index("cards", replace=True)
        await self.vectors.ensure_fts_index("sessions", replace=True)

        self._apply_retention()

        return {
            "status": "ok",
            "sessions": sessions_count,
            "cards": cards_count,
            "searches_replayed": searches_replayed,
            "errors_count": errors_count,
        }

    def _apply_retention(self) -> None:
        days = self.config.settings.search.search_log_retention_days
        if days <= 0:
            return
        cutoff = time.time() - days * 86400
        for p in list(self.config.search_log_dir.glob("*.jsonl")):
            if p.stat().st_mtime < cutoff:
                p.unlink()
