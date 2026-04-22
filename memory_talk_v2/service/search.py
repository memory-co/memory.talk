"""Search service — hybrid FTS+vector over cards, FTS-only over sessions, with
DSL whitelist filter and full-response SearchLog persistence.
"""
from __future__ import annotations
import json

from memory_talk_v2.config import Config
from memory_talk_v2.dsl import compile_for, parse, DSLError
from memory_talk_v2.embedding import Embedder
from memory_talk_v2.ids import new_search_id
from memory_talk_v2.service.snippet import extract_snippets
from memory_talk_v2.service.ttl import current_ttl, dt_to_iso, now_utc
from memory_talk_v2.storage.jsonl_writer import DatedJsonlWriter
from memory_talk_v2.storage.lancedb import LanceStore
from memory_talk_v2.storage.sqlite import SQLiteStore


class SearchError(ValueError):
    pass


def _link_to_ref(link: dict, object_id: str, now) -> dict:
    if link["source_id"] == object_id:
        peer_id = link["target_id"]; peer_type = link["target_type"]
    else:
        peer_id = link["source_id"]; peer_type = link["source_type"]
    return {
        "link_id": link["link_id"],
        "target_id": peer_id,
        "target_type": peer_type,
        "comment": link["comment"],
        "ttl": current_ttl(link["expires_at"], now),
    }


def _active_links(db: SQLiteStore, object_id: str, now) -> list[dict]:
    """Load links touching object_id, drop expired user links (ttl < 0)."""
    out: list[dict] = []
    for l in db.links_touching(object_id):
        ref = _link_to_ref(l, object_id, now)
        if ref["ttl"] < 0:
            continue
        out.append(ref)
    return out


def _dsl_whitelists(db: SQLiteStore, where: str | None) -> tuple[list[str] | None, list[str] | None]:
    """Return (card_whitelist, session_whitelist). None means no filter. Empty means no matches."""
    if not where:
        return None, None
    preds = parse(where)
    card_result = compile_for(preds, "cards")
    sess_result = compile_for(preds, "sessions")

    card_wl: list[str] | None
    if card_result is None:
        card_wl = []   # DSL has sessions-only fields, so cards can never match
    else:
        sql, params = card_result
        rows = db.conn.execute(f"SELECT card_id FROM cards WHERE {sql}", params).fetchall()
        card_wl = [r[0] for r in rows]

    sess_wl: list[str] | None
    if sess_result is None:
        sess_wl = []
    else:
        sql, params = sess_result
        rows = db.conn.execute(f"SELECT session_id FROM sessions WHERE {sql}", params).fetchall()
        sess_wl = [r[0] for r in rows]
    return card_wl, sess_wl


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


def search(
    payload: dict,
    *,
    config: Config,
    db: SQLiteStore,
    vectors: LanceStore,
    embedder: Embedder,
    search_jsonl: DatedJsonlWriter,
) -> dict:
    query = payload.get("query", "") or ""
    where = payload.get("where")
    top_k = payload.get("top_k") or config.settings.search.default_top_k
    if top_k <= 0 or top_k > 1000:
        raise SearchError("top_k out of range (1..1000)")

    try:
        card_wl, sess_wl = _dsl_whitelists(db, where)
    except DSLError as e:
        raise SearchError(f"DSL parse error: {e}")

    now = now_utc()
    created_at = dt_to_iso(now)
    search_id = new_search_id()

    # LanceDB FTS doesn't auto-absorb appended rows — ensure/optimize before query.
    vectors.ensure_fts_index("cards")
    vectors.ensure_fts_index("sessions")

    # ---- cards ----
    card_hits: list[dict] = []
    if card_wl is not None and len(card_wl) == 0:
        pass  # DSL filter excludes everything on the cards side
    else:
        if query.strip():
            vector = embedder.embed_one(query)
            raw = vectors.hybrid_search_cards(vector, query, whitelist=card_wl, top_k=top_k)
            for rank, hit in enumerate(raw, start=1):
                card_id = hit.get("card_id")
                c = db.get_card(card_id)
                if not c:
                    continue
                snip_src = _cards_text_for_snippet(c)
                card_hits.append({
                    "card_id": card_id,
                    "rank": rank,
                    "score": float(hit.get("_relevance_score") or hit.get("_score") or 0.0),
                    "summary": c["summary"],
                    "snippets": extract_snippets(snip_src, query),
                    "links": _active_links(db, card_id, now),
                })
        else:
            # Pure metadata-filter path: list cards sorted by created_at desc
            sql = "SELECT card_id, summary, created_at FROM cards"
            params: list = []
            if card_wl is not None:
                placeholders = ",".join("?" * len(card_wl)) or "NULL"
                sql += f" WHERE card_id IN ({placeholders})"
                params.extend(card_wl)
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(top_k)
            rows = db.conn.execute(sql, params).fetchall()
            for rank, r in enumerate(rows, start=1):
                card_id = r["card_id"]
                card_hits.append({
                    "card_id": card_id, "rank": rank, "score": 0.0,
                    "summary": r["summary"], "snippets": [],
                    "links": _active_links(db, card_id, now),
                })

    # ---- sessions ----
    sess_hits: list[dict] = []
    if sess_wl is not None and len(sess_wl) == 0:
        pass
    else:
        if query.strip():
            raw = vectors.fts_search_sessions(query, whitelist=sess_wl, top_k=top_k)
            for rank, hit in enumerate(raw, start=1):
                sid = hit.get("session_id")
                s = db.get_session(sid)
                if not s:
                    continue
                rounds = db.list_rounds(sid)
                snip_src = _session_text_for_snippet(rounds)
                sess_hits.append({
                    "session_id": sid, "rank": rank,
                    "score": float(hit.get("_score") or 0.0),
                    "source": s["source"], "tags": s["tags"],
                    "snippets": extract_snippets(snip_src, query),
                    "links": _active_links(db, sid, now),
                })
        else:
            sql = "SELECT session_id, source, tags, created_at FROM sessions"
            params: list = []
            if sess_wl is not None:
                placeholders = ",".join("?" * len(sess_wl)) or "NULL"
                sql += f" WHERE session_id IN ({placeholders})"
                params.extend(sess_wl)
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(top_k)
            rows = db.conn.execute(sql, params).fetchall()
            for rank, r in enumerate(rows, start=1):
                sid = r["session_id"]
                sess_hits.append({
                    "session_id": sid, "rank": rank, "score": 0.0,
                    "source": r["source"], "tags": json.loads(r["tags"] or "[]"),
                    "snippets": [], "links": _active_links(db, sid, now),
                })

    response = {
        "search_id": search_id,
        "query": query,
        "cards": {"count": len(card_hits), "results": card_hits},
        "sessions": {"count": len(sess_hits), "results": sess_hits},
    }

    # Persist FULL response to search_log + jsonl
    persisted = {
        "search_id": search_id, "query": query, "where": where,
        "top_k": top_k, "created_at": created_at,
        "cards": response["cards"], "sessions": response["sessions"],
    }
    search_jsonl.append(persisted, now=now)
    db.insert_search_log(
        search_id=search_id, query=query, where_dsl=where,
        top_k=top_k, created_at=created_at,
        response_json=json.dumps(persisted, ensure_ascii=False),
    )

    return response
