"""Memory Talk API package."""
from fastapi import APIRouter

from memory_talk.api import conversations, ingest, search, sources, status

router = APIRouter()
router.include_router(ingest.router)
router.include_router(conversations.router)
router.include_router(search.router)
router.include_router(sources.router)
router.include_router(status.router)

# Global source manager (will be set by web app)
source_manager = None


def set_source_manager(manager):
    """Set the global source manager for all API modules."""
    global source_manager
    source_manager = manager
    # Also set it in submodules
    sources.set_source_manager(manager)
    status.set_source_manager(manager)
