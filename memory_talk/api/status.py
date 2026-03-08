"""Status API endpoints."""
from fastapi import APIRouter

from memory_talk.models import ServerStatus
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


@router.get("/api/status")
async def get_server_status() -> dict:
    """Get overall server status.

    Returns:
        Server status
    """
    total_conversations, total_messages = storage.get_stats()

    sources = []
    if source_manager is not None:
        sources = source_manager.get_all_status()

    return ServerStatus(
        version="0.1.0",
        sources=sources,
        total_conversations=total_conversations,
        total_messages=total_messages,
        uptime="running",  # TODO: track actual uptime
    ).model_dump(mode="json")
