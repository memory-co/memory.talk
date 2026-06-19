"""POST /v3/insights + GET /v3/insights + PATCH /v3/insights/{cid}/tags.

Card read is via ``POST /v3/read`` (no ``GET /v3/insights/{cid}`` — read is
the universal entry point keyed by id prefix). List + tag PATCH are
maintenance endpoints, designed to mirror the session counterparts so
the two object types' management UX stays consistent.
"""
from __future__ import annotations

import datetime as _dt

from fastapi import APIRouter, HTTPException, Query, Request

from memorytalk.schemas import (
    InsightDeleteResponse, InsightListResponse, InsightMeta, InsightTagResponse,
    CreateInsightRequest, CreateInsightResponse,
    TagPatchRequest,
)
from memorytalk.service import InsightConflict, InsightServiceError
from memorytalk.service.insights import InsightNotFound
from memorytalk.util.tag_filter import parse_tag_arg
from memorytalk.util.tags import TagValidationError, apply_patch


router = APIRouter()


@router.post("/insights", response_model=CreateInsightResponse)
async def post_cards(payload: CreateInsightRequest, request: Request) -> CreateInsightResponse:
    svc = request.app.state.insights
    if svc is None:
        raise HTTPException(status_code=503, detail="cards service unavailable")
    try:
        card_id = await svc.create(payload)
    except InsightConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except InsightServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CreateInsightResponse(card_id=card_id)


# ─── 0.8.x: list + tag maintenance ──────────────────────────────────


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
    """Parse repeated ``?tag=...`` params via the shared tag_filter
    parser — same 5-form vocabulary used by session list."""
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
async def get_cards(
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
    # Derived recall_count merge — list_cards strips it (column no
    # longer exists), recall_event is the source of truth.
    if rows:
        counts = await request.app.state.db.recall.recall_counts(
            [r["card_id"] for r in rows]
        )
        for r in rows:
            (r["stats"] or {}).setdefault(
                "recall_count", counts.get(r["card_id"], 0),
            )
            if r.get("stats") is None:
                r["stats"] = {"recall_count": counts.get(r["card_id"], 0)}
            else:
                r["stats"]["recall_count"] = counts.get(r["card_id"], 0)
    cards = [
        InsightMeta(
            card_id=r["card_id"],
            insight=r["insight"],
            created_at=r["created_at"],
            tags=r.get("tags") or {},
            stats=r.get("stats") or {},
        )
        for r in rows
    ]
    return InsightListResponse(total=total, returned=len(cards), cards=cards)


@router.patch("/insights/{card_id}/tags", response_model=InsightTagResponse)
async def patch_card_tags(
    card_id: str, payload: TagPatchRequest, request: Request,
):
    """Set / unset / query tags. Empty body = query (returns current
    tags unchanged). Validates before any write — partial application
    is impossible by construction."""
    store = request.app.state.db.insights
    current = await store.get_tags(card_id)
    if current is None:
        raise HTTPException(
            status_code=404, detail=f"card {card_id!r} not found",
        )

    try:
        merged = apply_patch(current, payload.set, payload.unset)
    except TagValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if payload.set or payload.unset:
        ok = await store.replace_tags(card_id, merged)
        if not ok:
            raise HTTPException(
                status_code=404, detail=f"card {card_id!r} not found",
            )
    return InsightTagResponse(card_id=card_id, tags=merged)


@router.delete("/insights/{card_id}", response_model=InsightDeleteResponse)
async def delete_card(card_id: str, request: Request) -> InsightDeleteResponse:
    """Hard-delete a card: SQLite row + reviews + outbound source_cards
    + vector embedding + per-card filesystem dir.

    Inbound source_cards (other cards that reference this one) are NOT
    cascaded — they become dangling references, which the response
    surfaces as ``inbound_refs_dangling`` so callers can warn the
    user. recall_event rows that mention this card_id are NOT touched
    — they're historical records, deleting the card doesn't rewrite
    history."""
    svc = request.app.state.insights
    if svc is None:
        raise HTTPException(status_code=503, detail="cards service unavailable")
    try:
        result = await svc.delete(card_id)
    except InsightNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    return InsightDeleteResponse(**result)
