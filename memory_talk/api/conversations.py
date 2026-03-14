"""Conversations API endpoints."""
from typing import Optional

from fastapi import APIRouter

from memory_talk.storage import Storage

router = APIRouter(tags=["Conversations"])
storage = Storage()


@router.get("/api/v1/conversations")
async def list_conversations(platform: Optional[str] = None) -> list[dict]:
    """List all conversations.

    Args:
        platform: Optional platform filter

    Returns:
        List of conversation summaries
    """
    conversations = storage.list_conversations(platform)
    return [conv.model_dump(mode="json") for conv in conversations]


@router.get("/api/v1/messages", tags=["Messages"])
async def get_messages(
    platform: Optional[str] = None,
    conversation_id: Optional[str] = None,
    role: Optional[str] = None,
    subject_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Get messages with filtering and pagination."""
    total, messages = storage.get_messages(
        platform=platform,
        conversation_id=conversation_id,
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


@router.delete("/api/v1/conversations")
async def delete_conversations(
    platform: str,
    conversation_id: Optional[str] = None,
) -> dict:
    """Delete conversations.

    Args:
        platform: Platform name (required)
        conversation_id: Optional conversation ID. If provided, deletes only that conversation.
                      If not provided, deletes all conversations for the platform.

    Returns:
        Number of conversations deleted
    """
    deleted_count = storage.delete_conversations(platform, conversation_id)
    return {
        "message": f"Deleted {deleted_count} conversation(s)",
        "deleted_count": deleted_count,
        "platform": platform,
        "conversation_id": conversation_id,
    }
