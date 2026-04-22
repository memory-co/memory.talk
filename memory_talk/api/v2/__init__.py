"""v2 API router aggregator."""
from fastapi import APIRouter

from memory_talk.api.v2.status import router as status_router

router = APIRouter()
router.include_router(status_router)
