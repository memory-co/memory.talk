"""Search service — FTS + vector hybrid for cards, FTS for sessions, DSL-filtered."""
from __future__ import annotations
import time
from datetime import datetime
from typing import Optional

from memory_talk.config import Config
from memory_talk.dsl import (
    Predicate,
    build_cards_where,
    build_sessions_where,
    parse,
)
from memory_talk.embedding import get_embedder
from memory_talk.service.ttl import compute_ttl
from memory_talk.storage.lancedb import LanceStore
from memory_talk.storage.sqlite import SQLiteStore


MAX_WHITELIST = 5000


class SearchService:
    def __init__(self, config: Config):
        self.config = config
        self.db = SQLiteStore(config.db_path)
        self.vectors = LanceStore(config.vectors_dir, dim=config.settings.embedding.dim)
        self.embedder = get_embedder(config)

    def search(
        self,
        query: str,
        where: Optional[str] = None,
        top_k: int = 10,
    ) -> dict:
        predicates = parse(where) if where else []
        now = datetime.now()
        return {
            "query": query,
            "where": where,
            "cards": self._search_cards(query, predicates, top_k, now),
            "sessions": self._search_sessions(query, predicates, top_k, now),
        }

    # ---------- cards ----------

    def _search_cards(
        self,
        query: str,
        predicates: list[Predicate],
        top_k: int,
        now: datetime,
    ) -> dict:
        where_sql, where_params = build_cards_where(predicates, now=now)
        has_dsl = bool(predicates)

        # Build whitelist via SQLite when DSL is present.
        whitelist: Optional[list[str]] = None
        if has_dsl:
            base_sql = (
                "SELECT c.card_id FROM cards c "
                "LEFT JOIN sessions s ON c.session_id = s.session_id "
                "WHERE c.expires_at > ?"
            )
            params: list = [time.time()]
            if where_sql:
                base_sql += " AND " + where_sql
                params.extend(where_params)
            rows = self.db.conn.execute(base_sql, params).fetchall()
            whitelist = [r["card_id"] for r in rows]
            if len(whitelist) > MAX_WHITELIST:
                raise ValueError(
                    f"cards whitelist too large ({len(whitelist)} > {MAX_WHITELIST}); tighten --where"
                )
            if not whitelist:
                return {"results": [], "count": 0}

        # Empty query → SQLite-only: most recent N from whitelist (or from all TTL-alive).
        if not query.strip():
            rows = self._recent_cards(whitelist, top_k)
            results = [r for r in (self._enrich_card(cid, 0.0) for cid in rows) if r]
            return {"results": results, "count": len(results)}

        # Hybrid search.
        vector = self.embedder.embed_one(query)
        hits = self.vectors.hybrid_search_cards(vector, query, whitelist, top_k)
        results = []
        for hit in hits:
            card_id = hit["card_id"]
            score = hit.get("_relevance_score", 0.0)
            enriched = self._enrich_card(card_id, score)
            if enriched:
                results.append(enriched)
        return {"results": results, "count": len(results)}

    def _recent_cards(self, whitelist: Optional[list[str]], top_k: int) -> list[str]:
        sql = "SELECT card_id FROM cards WHERE expires_at > ?"
        params: list = [time.time()]
        if whitelist is not None:
            if not whitelist:
                return []
            placeholders = ", ".join("?" for _ in whitelist)
            sql += f" AND card_id IN ({placeholders})"
            params.extend(whitelist)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(top_k)
        return [r["card_id"] for r in self.db.conn.execute(sql, params).fetchall()]

    def _enrich_card(self, card_id: str, score: float) -> Optional[dict]:
        db_card = self.db.get_card(card_id)
        if not db_card:
            return None
        ttl = compute_ttl(db_card["expires_at"])
        if ttl <= 0:
            return None
        links_raw = self.db.get_links(card_id)
        links = [
            {
                "link_id": lk["link_id"],
                "id": lk["target_id"] if lk["source_id"] == card_id else lk["source_id"],
                "type": lk["target_type"] if lk["source_id"] == card_id else lk["source_type"],
                "comment": lk.get("comment"),
                "ttl": compute_ttl(lk["expires_at"]),
            }
            for lk in links_raw
            if compute_ttl(lk["expires_at"]) > 0
        ]
        return {
            "card_id": card_id,
            "summary": db_card["summary"],
            "session_id": db_card["session_id"],
            "ttl": ttl,
            "score": score,
            "links": links,
        }

    # ---------- sessions ----------

    def _search_sessions(
        self,
        query: str,
        predicates: list[Predicate],
        top_k: int,
        now: datetime,
    ) -> dict:
        compiled = build_sessions_where(predicates, now=now)
        if compiled is None:
            # cards-only field present → sessions side is inexpressible
            return {"results": [], "count": 0}
        where_sql, where_params = compiled
        has_dsl = bool(predicates)

        whitelist: Optional[list[str]] = None
        if has_dsl:
            base_sql = "SELECT s.session_id FROM sessions s"
            params: list = []
            if where_sql:
                base_sql += " WHERE " + where_sql
                params.extend(where_params)
            rows = self.db.conn.execute(base_sql, params).fetchall()
            whitelist = [r["session_id"] for r in rows]
            if len(whitelist) > MAX_WHITELIST:
                raise ValueError(
                    f"sessions whitelist too large ({len(whitelist)} > {MAX_WHITELIST}); tighten --where"
                )
            if not whitelist:
                return {"results": [], "count": 0}

        if not query.strip():
            rows = self._recent_sessions(whitelist, top_k)
            results = [self._enrich_session(sid, 0.0) for sid in rows]
            return {"results": [r for r in results if r], "count": len([r for r in results if r])}

        hits = self.vectors.fts_search_sessions(query, whitelist, top_k)
        results = []
        for hit in hits:
            sid = hit["session_id"]
            score = hit.get("_score", 0.0)
            enriched = self._enrich_session(sid, score)
            if enriched:
                results.append(enriched)
        return {"results": results, "count": len(results)}

    def _recent_sessions(self, whitelist: Optional[list[str]], top_k: int) -> list[str]:
        sql = "SELECT session_id FROM sessions"
        params: list = []
        if whitelist is not None:
            if not whitelist:
                return []
            placeholders = ", ".join("?" for _ in whitelist)
            sql += f" WHERE session_id IN ({placeholders})"
            params.extend(whitelist)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(top_k)
        return [r["session_id"] for r in self.db.conn.execute(sql, params).fetchall()]

    def _enrich_session(self, session_id: str, score: float) -> Optional[dict]:
        row = self.db.conn.execute(
            "SELECT session_id, source, tags, round_count, created_at FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        import json
        return {
            "session_id": row["session_id"],
            "source": row["source"],
            "tags": json.loads(row["tags"] or "[]"),
            "round_count": row["round_count"],
            "created_at": row["created_at"],
            "score": score,
        }
