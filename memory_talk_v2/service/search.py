"""Search service — hybrid FTS + vector over cards, FTS-only over sessions. All async."""
from __future__ import annotations
import json

from memory_talk_v2.config import Config
from memory_talk_v2.util.dsl import DSLError, compile_for, parse
from memory_talk_v2.embedding import Embedder
from memory_talk_v2.util.ids import new_search_id
from memory_talk_v2.service.links import link_to_ref
from memory_talk_v2.util.snippet import extract_snippets
from memory_talk_v2.util.ttl import dt_to_iso, now_utc
from memory_talk_v2.storage.jsonl_writer import DatedJsonlWriter
from memory_talk_v2.storage.lancedb import LanceStore
from memory_talk_v2.storage.sqlite import SQLiteStore


class SearchError(ValueError):
    """400 — invalid input or DSL parse error."""


def _cards_text_for_snippet(card: dict) -> str:
    rounds_text = "\n".join(r.get("text") or "" for r in card["rounds"])
    return card["summary"] + ("\n" + rounds_text if rounds_text else "")


def _session_text_for_snippet(rounds: list[dict]) -> str:
    parts: list[str] = []
    for r in rounds:
        for b in r.get("content") or []:
            t = b.get("type")
            if t in ("text", "code"):
                parts.append(b.get("text") or "")
            elif t == "thinking":
                parts.append(b.get("thinking") or "")
    return "\n".join(p for p in parts if p)


class SearchService:
    def __init__(
        self, *,
        config: Config,
        db: SQLiteStore,
        vectors: LanceStore,
        embedder: Embedder,
        search_jsonl: DatedJsonlWriter,
    ):
        self.config = config
        self.db = db
        self.vectors = vectors
        self.embedder = embedder
        self.search_jsonl = search_jsonl

    async def search(self, payload: dict) -> dict:
        query = payload.get("query", "") or ""
        where = payload.get("where")
        top_k = payload.get("top_k") or self.config.settings.search.default_top_k
        if top_k <= 0 or top_k > 1000:
            raise SearchError("top_k out of range (1..1000)")

        try:
            card_wl, sess_wl = await self._dsl_whitelists(where)
        except DSLError as e:
            raise SearchError(f"DSL parse error: {e}")

        now = now_utc()
        created_at = dt_to_iso(now)
        search_id = new_search_id()

        await self.vectors.ensure_fts_index("cards")
        await self.vectors.ensure_fts_index("sessions")

        card_hits = await self._search_cards(query, card_wl, top_k, now)
        sess_hits = await self._search_sessions(query, sess_wl, top_k, now)

        response = {
            "search_id": search_id, "query": query,
            "cards": {"count": len(card_hits), "results": card_hits},
            "sessions": {"count": len(sess_hits), "results": sess_hits},
        }

        persisted = {
            "search_id": search_id, "query": query, "where": where,
            "top_k": top_k, "created_at": created_at,
            "cards": response["cards"], "sessions": response["sessions"],
        }
        await self.search_jsonl.append(persisted, now=now)
        await self.db.insert_search_log(
            search_id=search_id, query=query, where_dsl=where,
            top_k=top_k, created_at=created_at,
            response_json=json.dumps(persisted, ensure_ascii=False),
        )

        return response

    async def _dsl_whitelists(self, where: str | None) -> tuple[list[str] | None, list[str] | None]:
        if not where:
            return None, None
        preds = parse(where)
        card_result = compile_for(preds, "cards")
        sess_result = compile_for(preds, "sessions")

        card_wl: list[str] | None
        if card_result is None:
            card_wl = []
        else:
            sql, params = card_result
            card_wl = await self.db.dsl_cards_whitelist(sql, params)

        sess_wl: list[str] | None
        if sess_result is None:
            sess_wl = []
        else:
            sql, params = sess_result
            sess_wl = await self.db.dsl_sessions_whitelist(sql, params)
        return card_wl, sess_wl

    async def _active_links(self, object_id: str, now) -> list[dict]:
        out: list[dict] = []
        for l in await self.db.links_touching(object_id):
            ref = link_to_ref(l, object_id, now)
            if ref["ttl"] < 0:
                continue
            out.append(ref)
        return out

    async def _search_cards(self, query, whitelist, top_k, now) -> list[dict]:
        hits: list[dict] = []
        if whitelist is not None and len(whitelist) == 0:
            return hits
        if query.strip():
            vector = await self.embedder.embed_one(query)
            raw = await self.vectors.hybrid_search_cards(vector, query, whitelist=whitelist, top_k=top_k)
            for rank, h in enumerate(raw, start=1):
                cid = h.get("card_id")
                c = await self.db.get_card(cid)
                if not c:
                    continue
                hits.append({
                    "card_id": cid, "rank": rank,
                    "score": float(h.get("_relevance_score") or h.get("_score") or 0.0),
                    "summary": c["summary"],
                    "snippets": extract_snippets(_cards_text_for_snippet(c), query),
                    "links": await self._active_links(cid, now),
                })
        else:
            rows = await self.db.cards_metadata_filtered(whitelist, top_k)
            for rank, r in enumerate(rows, start=1):
                cid = r["card_id"]
                hits.append({
                    "card_id": cid, "rank": rank, "score": 0.0,
                    "summary": r["summary"], "snippets": [],
                    "links": await self._active_links(cid, now),
                })
        return hits

    async def _search_sessions(self, query, whitelist, top_k, now) -> list[dict]:
        hits: list[dict] = []
        if whitelist is not None and len(whitelist) == 0:
            return hits
        if query.strip():
            raw = await self.vectors.fts_search_sessions(query, whitelist=whitelist, top_k=top_k)
            for rank, h in enumerate(raw, start=1):
                sid = h.get("session_id")
                s = await self.db.get_session(sid)
                if not s:
                    continue
                rounds = await self.db.list_rounds(sid)
                hits.append({
                    "session_id": sid, "rank": rank,
                    "score": float(h.get("_score") or 0.0),
                    "source": s["source"], "tags": s["tags"],
                    "snippets": extract_snippets(_session_text_for_snippet(rounds), query),
                    "links": await self._active_links(sid, now),
                })
        else:
            rows = await self.db.sessions_metadata_filtered(whitelist, top_k)
            for rank, r in enumerate(rows, start=1):
                hits.append({
                    "session_id": r["session_id"], "rank": rank, "score": 0.0,
                    "source": r["source"], "tags": r["tags"],
                    "snippets": [], "links": await self._active_links(r["session_id"], now),
                })
        return hits
