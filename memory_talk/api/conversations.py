"""Conversations API endpoints."""
from typing import Optional

from fastapi import APIRouter, HTTPException

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


@router.get("/api/conversations/{platform}/{session_id}")
async def get_conversation(
    platform: str,
    session_id: str,
) -> dict:
    """Get a specific conversation.

    Args:
        platform: Platform name
        session_id: Session ID

    Returns:
        Conversation data
    """
    result = storage.get_conversation(platform, session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    metadata, messages = result
    return {
        "metadata": metadata.model_dump(mode="json"),
        "messages": [msg.model_dump(mode="json") for msg in messages],
    }
