"""Conversations API endpoints."""
from typing import Optional

from fastapi import APIRouter

from memory_talk.storage import Storage

router = APIRouter()
storage = Storage()


@router.get("/api/conversations")
async def list_conversations(platform: Optional[str] = None) -> list[dict]:
    """List all conversations.

    Args:
        platform: Optional platform filter

    Returns:
        List of conversation summaries
    """
    conversations = storage.list_conversations(platform)
    return [conv.model_dump(mode="json") for conv in conversations]


@router.get("/api/messages")
async def get_messages(
    platform: Optional[str] = None,
    session_id: Optional[str] = None,
    role: Optional[str] = None,
    subject_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Get messages with filtering and pagination."""
    total, messages = storage.get_messages(
        platform=platform,
        session_id=session_id,
        role=role,
        subject_id=subject_id,
        limit=limit,
        offset=offset,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "messages": [msg.model_dump(mode="json") for msg in messages],
    }
