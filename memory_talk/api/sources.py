"""Sources API endpoints."""
from fastapi import APIRouter

from memory_talk.storage import Storage

router = APIRouter()
storage = Storage()

# Global source manager (will be set by web app)
source_manager = None


def get_source_manager():
    """Get the global source manager."""
    return source_manager


def set_source_manager(manager):
    """Set the global source manager."""
    global source_manager
    source_manager = manager


@router.get("/api/sources")
async def list_sources() -> list[dict]:
    """List all sources and their status.

    Returns:
        List of source statuses
    """
    if source_manager is None:
        return []

    sources = source_manager.get_all_status()
    return [s.model_dump(mode="json") for s in sources]
