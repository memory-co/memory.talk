"""Message mapper functions."""
import json
from datetime import datetime
from typing import Optional

from memory_talk.storage.repository.domain.message import MessageDO


def row_to_message_do(row: Optional[tuple]) -> Optional[MessageDO]:
    """Convert database row to MessageDO.

    Args:
        row: Database row tuple

    Returns:
        MessageDO or None if row is None
    """
    if row is None:
        return None

    return MessageDO(
        uuid=row[0],
        parent_uuid=row[1],
        platform=row[2],
        conversation_id=row[3],
        role=row[4],
        subject_id=row[5],
        content=row[6],
        timestamp=row[7],
        attachments=json.loads(row[8]) if row[8] else [],
        metadata=json.loads(row[9]) if row[9] else {},
    )


def message_do_to_row(do: MessageDO) -> dict:
    """Convert MessageDO to database row dict.

    Args:
        do: MessageDO

    Returns:
        Dictionary for SQL insertion
    """
    return {
        "uuid": do.uuid,
        "parent_uuid": do.parent_uuid,
        "platform": do.platform,
        "conversation_id": do.conversation_id,
        "role": do.role,
        "subject_id": do.subject_id,
        "content": do.content,
        "timestamp": do.timestamp,
        "attachments": json.dumps([a.model_dump() if hasattr(a, 'model_dump') else a for a in do.attachments]),
        "metadata": json.dumps(do.metadata),
    }
