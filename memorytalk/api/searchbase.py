"""/v4/searchbase — the searchbase admin surface (reembed only).

The one HTTP admin operation searchbase exposes: ``reembed`` recomputes
all vectors and overwrites the index. Triggered by setup when
``embedding.dim`` changes; not for end users. See
``docs/api/v4/searchbase.md``.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from memorytalk.api._card_common import require
from memorytalk.service.reembed import (
    ReembedDimMismatch, ReembedInProgress, ReembedProviderDown,
)

router = APIRouter()


class ReembedRequest(BaseModel):
    # ``expected_dim`` is required by the contract, but declared optional
    # here so a missing value yields the contract's 400 (handled below)
    # rather than FastAPI's default 422. The server reloads its own
    # settings dim and refuses unless it matches — guards against wiping
    # vectors at the wrong dim when setup/server state has skewed.
    expected_dim: int | None = None
    dry_run: bool = False


@router.post("/searchbase/reembed")
async def post_reembed(payload: ReembedRequest, request: Request):
    svc = require(getattr(request.app.state, "reembed", None), "searchbase")
    if payload.expected_dim is None:
        raise HTTPException(status_code=400, detail="expected_dim required")
    try:
        return await svc.reembed(payload.expected_dim, dry_run=payload.dry_run)
    except ReembedDimMismatch as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ReembedInProgress as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ReembedProviderDown as e:
        # 500 but with the processed-so-far count in the body (not a bare
        # error) so the caller knows how far the interrupted run got.
        raise HTTPException(
            status_code=500,
            detail={"error": str(e), "cards_processed": e.processed},
        )
