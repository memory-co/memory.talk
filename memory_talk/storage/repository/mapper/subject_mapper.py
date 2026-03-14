"""Subject mapper functions."""
import json
from datetime import datetime
from typing import Optional

from memory_talk.storage.repository.domain.subject import SubjectDO


def row_to_subject_do(row: Optional[tuple]) -> Optional[SubjectDO]:
    """Convert database row to SubjectDO.

    Args:
        row: Database row tuple

    Returns:
        SubjectDO or None if row is None
    """
    if row is None:
        return None

    return SubjectDO(
        id=row[0],
        name=row[1],
        metadata=json.loads(row[2]) if row[2] else {},
        created_at=row[3],
        updated_at=row[4],
    )


def subject_do_to_row(do: SubjectDO) -> dict:
    """Convert SubjectDO to database row dict.

    Args:
        do: SubjectDO

    Returns:
        Dictionary for SQL insertion
    """
    return {
        "id": do.id,
        "name": do.name,
        "metadata": json.dumps(do.metadata),
        "created_at": do.created_at,
        "updated_at": do.updated_at,
    }
