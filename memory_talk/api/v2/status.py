"""GET /v2/status — stats for the v2 layer.

Deliberately reads counts out of the v2 SQLite tables (falling back
to shared v1 tables for sessions/cards/links, which v2 will ingest
into in later plans).
"""
from __future__ import annotations
import sqlite3

from fastapi import APIRouter, Request

router = APIRouter()


def _count(conn: sqlite3.Connection, table: str) -> int:
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.OperationalError:
        return 0


@router.get("/status")
async def get_status(request: Request) -> dict:
    config = request.app.state.config
    with sqlite3.connect(config.db_path) as conn:
        sessions_total = _count(conn, "sessions")
        cards_total = _count(conn, "cards")
        links_total = _count(conn, "links")
        searches_total = _count(conn, "search_log")

    return {
        "data_root": str(config.data_root),
        "settings_path": str(config.settings_path),
        "status": "running",
        "sessions_total": sessions_total,
        "cards_total": cards_total,
        "links_total": links_total,
        "searches_total": searches_total,
        "vector_provider": config.settings.vector.provider,
        "relation_provider": config.settings.relation.provider,
        "embedding_provider": config.settings.embedding.provider,
    }
