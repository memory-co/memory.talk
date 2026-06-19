"""GET /v4/insights — read-only list/search of the old v3 card ("insight").

Insight is read-only in v4: data is preserved (list here + view via
``POST /v4/read`` with an ``insight_`` id). No create / tag / delete.
"""
from __future__ import annotations

import datetime as _dt

from fastapi import APIRouter, HTTPException, Query, Request

from memorytalk.schemas import InsightListResponse, InsightMeta
from memorytalk.util.tag_filter import parse_tag_arg
from memorytalk.util.tags import TagValidationError


router = APIRouter()


def _parse_iso(value: str | None, *, field: str) -> str | None:
    if value is None:
        return None
    try:
        _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400, detail=f"invalid ISO 8601 in '{field}': {value!r}",
        )
    return value


def _parse_tag_filters(raw: list[str]):
    """Parse repeated ``?tag=...`` params via the shared tag_filter parser."""
    preds = []
    try:
        for item in raw:
            if not item:
                continue
            preds.append(parse_tag_arg(item))
    except TagValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return preds


@router.get("/insights", response_model=InsightListResponse)
async def get_insights(
    request: Request,
    tag: list[str] = Query(default_factory=list),
    since: str | None = Query(None),
    until: str | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
):
    since_iso = _parse_iso(since, field="since")
    until_iso = _parse_iso(until, field="until")
    if since_iso and until_iso and since_iso > until_iso:
        raise HTTPException(
            status_code=400, detail="'since' must be <= 'until'",
        )
    tag_filters = _parse_tag_filters(tag)

    total, rows = await request.app.state.db.insights.list_cards(
        tag_filters=tag_filters,
        since=since_iso,
        until=until_iso,
        limit=limit,
    )
    # Derived recall_count merge — list_cards strips it (column no longer
    # exists), recall_event is the source of truth.
    if rows:
        counts = await request.app.state.db.recall.recall_counts(
            [r["insight_id"] for r in rows]
        )
        for r in rows:
            stats = r.get("stats") or {}
            stats["recall_count"] = counts.get(r["insight_id"], 0)
            r["stats"] = stats
    cards = [
        InsightMeta(
            insight_id=r["insight_id"],
            insight=r["insight"],
            created_at=r["created_at"],
            tags=r.get("tags") or {},
            stats=r.get("stats") or {},
        )
        for r in rows
    ]
    return InsightListResponse(total=total, returned=len(cards), cards=cards)
