"""v1 API router aggregation."""
from __future__ import annotations
from fastapi import APIRouter

from memory_talk.api.v1 import sessions, cards, links, recall, search, status

router = APIRouter()
router.include_router(sessions.router)
router.include_router(cards.router)
router.include_router(links.router)
router.include_router(recall.router)
router.include_router(search.router)
router.include_router(status.router)
