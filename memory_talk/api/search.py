"""Search API endpoints."""
from fastapi import APIRouter

from memory_talk.storage import Storage

router = APIRouter()
storage = Storage()


@router.get("/api/search")
async def search_conversations(q: str) -> list[dict]:
    """Search conversations.

    Args:
        q: Search query

    Returns:
        List of search results
    """
    results = storage.search(q)
    return [result.model_dump(mode="json") for result in results]
