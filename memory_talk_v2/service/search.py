"""Search service — hybrid FTS + vector over cards, FTS-only over sessions,
DSL whitelist filter, full-response SearchLog persistence.
"""
from __future__ import annotations
import json

from memory_talk_v2.dsl import DSLError, compile_for, parse
from memory_talk_v2.ids import new_search_id
from memory_talk_v2.service.context import ServiceContext
from memory_talk_v2.service.links import link_to_ref
from memory_talk_v2.service.snippet import extract_snippets
from memory_talk_v2.service.ttl import current_ttl, dt_to_iso, now_utc


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
    def __init__(self, ctx: ServiceContext):
        self.ctx = ctx

    def search(self, payload: dict) -> dict:
        ctx = self.ctx
        query = payload.get("query", "") or ""
        where = payload.get("where")
        top_k = payload.get("top_k") or ctx.config.settings.search.default_top_k
        if top_k <= 0 or top_k > 1000:
            raise SearchError("top_k out of range (1..1000)")

        try:
            card_wl, sess_wl = self._dsl_whitelists(where)
        except DSLError as e:
            raise SearchError(f"DSL parse error: {e}")

        now = now_utc()
        created_at = dt_to_iso(now)
        search_id = new_search_id()

        ctx.vectors.ensure_fts_index("cards")
        ctx.vectors.ensure_fts_index("sessions")

        card_hits = self._search_cards(query, card_wl, top_k, now)
        sess_hits = self._search_sessions(query, sess_wl, top_k, now)

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
        ctx.search_jsonl.append(persisted, now=now)
        ctx.db.insert_search_log(
            search_id=search_id, query=query, where_dsl=where,
            top_k=top_k, created_at=created_at,
            response_json=json.dumps(persisted, ensure_ascii=False),
        )

        return response

    def _dsl_whitelists(self, where: str | None) -> tuple[list[str] | None, list[str] | None]:
        """Return (card_whitelist, session_whitelist). None means no filter on
        that side; empty means DSL can never match anything there."""
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
            rows = self.ctx.db.conn.execute(
                f"SELECT card_id FROM cards WHERE {sql}", params,
            ).fetchall()
            card_wl = [r[0] for r in rows]

        sess_wl: list[str] | None
        if sess_result is None:
            sess_wl = []
        else:
            sql, params = sess_result
            rows = self.ctx.db.conn.execute(
                f"SELECT session_id FROM sessions WHERE {sql}", params,
            ).fetchall()
            sess_wl = [r[0] for r in rows]
        return card_wl, sess_wl

    def _active_links(self, object_id: str, now) -> list[dict]:
        out: list[dict] = []
        for l in self.ctx.db.links_touching(object_id):
            ref = link_to_ref(l, object_id, now)
            if ref["ttl"] < 0:
                continue
            out.append(ref)
        return out

    def _search_cards(self, query, whitelist, top_k, now) -> list[dict]:
        ctx = self.ctx
        hits: list[dict] = []
        if whitelist is not None and len(whitelist) == 0:
            return hits
        if query.strip():
            vector = ctx.embedder.embed_one(query)
            raw = ctx.vectors.hybrid_search_cards(vector, query, whitelist=whitelist, top_k=top_k)
            for rank, h in enumerate(raw, start=1):
                cid = h.get("card_id")
                c = ctx.db.get_card(cid)
                if not c:
                    continue
                hits.append({
                    "card_id": cid, "rank": rank,
                    "score": float(h.get("_relevance_score") or h.get("_score") or 0.0),
                    "summary": c["summary"],
                    "snippets": extract_snippets(_cards_text_for_snippet(c), query),
                    "links": self._active_links(cid, now),
                })
        else:
            sql = "SELECT card_id, summary, created_at FROM cards"
            params: list = []
            if whitelist is not None:
                placeholders = ",".join("?" * len(whitelist)) or "NULL"
                sql += f" WHERE card_id IN ({placeholders})"
                params.extend(whitelist)
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(top_k)
            rows = ctx.db.conn.execute(sql, params).fetchall()
            for rank, r in enumerate(rows, start=1):
                cid = r["card_id"]
                hits.append({
                    "card_id": cid, "rank": rank, "score": 0.0,
                    "summary": r["summary"], "snippets": [],
                    "links": self._active_links(cid, now),
                })
        return hits

    def _search_sessions(self, query, whitelist, top_k, now) -> list[dict]:
        ctx = self.ctx
        hits: list[dict] = []
        if whitelist is not None and len(whitelist) == 0:
            return hits
        if query.strip():
            raw = ctx.vectors.fts_search_sessions(query, whitelist=whitelist, top_k=top_k)
            for rank, h in enumerate(raw, start=1):
                sid = h.get("session_id")
                s = ctx.db.get_session(sid)
                if not s:
                    continue
                rounds = ctx.db.list_rounds(sid)
                hits.append({
                    "session_id": sid, "rank": rank,
                    "score": float(h.get("_score") or 0.0),
                    "source": s["source"], "tags": s["tags"],
                    "snippets": extract_snippets(_session_text_for_snippet(rounds), query),
                    "links": self._active_links(sid, now),
                })
        else:
            sql = "SELECT session_id, source, tags, created_at FROM sessions"
            params: list = []
            if whitelist is not None:
                placeholders = ",".join("?" * len(whitelist)) or "NULL"
                sql += f" WHERE session_id IN ({placeholders})"
                params.extend(whitelist)
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(top_k)
            rows = ctx.db.conn.execute(sql, params).fetchall()
            for rank, r in enumerate(rows, start=1):
                sid = r["session_id"]
                hits.append({
                    "session_id": sid, "rank": rank, "score": 0.0,
                    "source": r["source"], "tags": json.loads(r["tags"] or "[]"),
                    "snippets": [], "links": self._active_links(sid, now),
                })
        return hits
