"""Shared helpers for the /v4 routers — service-exception → HTTP mapping."""
from __future__ import annotations

from fastapi import HTTPException

from memorytalk.service.cards import CardConflict, CardNotFound, CardServiceError


def http_from_service_error(e: Exception) -> HTTPException:
    """Map a CardService exception onto its HTTP status. CardConflict→409,
    CardNotFound→404, any other CardServiceError→400."""
    if isinstance(e, CardConflict):
        return HTTPException(status_code=409, detail=str(e))
    if isinstance(e, CardNotFound):
        return HTTPException(status_code=404, detail=str(e))
    if isinstance(e, CardServiceError):
        return HTTPException(status_code=400, detail=str(e))
    raise e


def require(svc, name: str):
    """503 when a service didn't initialize (e.g. searchbase missing)."""
    if svc is None:
        raise HTTPException(status_code=503, detail=f"{name} service unavailable")
    return svc
