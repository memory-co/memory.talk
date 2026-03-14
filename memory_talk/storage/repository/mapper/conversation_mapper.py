"""Conversation mapper functions."""
import json
from datetime import datetime
from typing import Optional

from memory_talk.storage.repository.domain.conversation import ConversationDO


def row_to_conversation_do(
    row: Optional[tuple],
) -> Optional[ConversationDO]:
    """Convert database row to ConversationDO.

    Args:
        row: Database row tuple

    Returns:
        ConversationDO or None if row is None
    """
    if row is None:
        return None

    return ConversationDO(
        conversation_id=row[0],
        platform=row[1],
        title=row[2],
        created_at=row[3],
        updated_at=row[4],
        participants=json.loads(row[5]) if row[5] else [],
        message_count=row[6],
    )


def conversation_do_to_row(do: ConversationDO) -> dict:
    """Convert ConversationDO to database row dict.

    Args:
        do: ConversationDO

    Returns:
        Dictionary for SQL insertion
    """
    return {
        "conversation_id": do.conversation_id,
        "platform": do.platform,
        "title": do.title,
        "created_at": do.created_at,
        "updated_at": do.updated_at,
        "participants": json.dumps([p.model_dump() if hasattr(p, 'model_dump') else p for p in do.participants]),
        "message_count": do.message_count,
    }
