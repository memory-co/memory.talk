"""Storage implementation for memory-talk using DuckDB."""
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import duckdb

from memory_talk.models import (
    ConversationSummary,
    Message,
    SearchResult,
    Subject,
)


class Storage:
    """Storage engine for conversation data using DuckDB."""

    def __init__(self, base_path: Optional[Path] = None):
        """Initialize storage.

        Args:
            base_path: Base directory for storing data. Defaults to ~/.talk-memory/
        """
        if base_path is None:
            # Check environment variable first
            env_path = os.environ.get("MEMORY_TALK_DATA_DIR")
            if env_path:
                base_path = Path(env_path)
            else:
                base_path = Path.home() / ".talk-memory"
        self.base_path = base_path
        self.blobs_dir = base_path / "blobs"
        self.db_path = base_path / "memory.duckdb"

        # Ensure directories exist
        self.blobs_dir.mkdir(parents=True, exist_ok=True)
        self.base_path.mkdir(parents=True, exist_ok=True)

        # Connect to DuckDB
        self.conn = duckdb.connect(str(self.db_path))
        self._init_schema()

    def _init_schema(self):
        """Initialize database schema."""
        # Create conversations table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                session_id VARCHAR,
                platform VARCHAR,
                title VARCHAR,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                participants JSON,
                message_count INTEGER,
                PRIMARY KEY (session_id, platform)
            )
        """)

        # Create subjects table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS subjects (
                id VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                metadata JSON,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
        """)

        # Create messages table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                uuid VARCHAR,
                parent_uuid VARCHAR,
                platform VARCHAR,
                session_id VARCHAR,
                role VARCHAR,
                subject_id VARCHAR REFERENCES subjects(id),
                content VARCHAR,
                timestamp TIMESTAMP,
                attachments JSON,
                metadata JSON,
                PRIMARY KEY (uuid, platform)
            )
        """)

        # Create indexes for better query performance
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_session
            ON messages(session_id, platform)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_content
            ON messages(content)
        """)

    def save_conversation(
        self,
        platform: str,
        session_id: str,
        messages: list[Message],
        metadata: dict,
    ) -> None:
        """Save a conversation.

        Args:
            platform: Platform name (e.g., 'chatgpt')
            session_id: Unique session identifier
            messages: List of messages
            metadata: Additional metadata
        """
        # Determine timestamps
        now = metadata.get("created_at", messages[0].timestamp if messages else datetime.now())
        if isinstance(now, str):
            now = datetime.fromisoformat(now.replace("Z", "+00:00"))

        title = metadata.get("title", f"Conversation {session_id}")
        participants = metadata.get("participants", [])
        participants_json = json.dumps([p.model_dump() for p in participants])

        # Check if conversation exists
        existing = self.conn.execute("""
            SELECT message_count FROM conversations
            WHERE session_id = ? AND platform = ?
        """, [session_id, platform]).fetchone()

        if existing:
            # Update existing conversation
            existing_count = existing[0]
            self.conn.execute("""
                UPDATE conversations
                SET title = ?, updated_at = ?, participants = ?, message_count = ?
                WHERE session_id = ? AND platform = ?
            """, [title, now, participants_json, existing_count + len(messages), session_id, platform])
        else:
            # Insert new conversation
            self.conn.execute("""
                INSERT INTO conversations (session_id, platform, title, created_at, updated_at, participants, message_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [session_id, platform, title, now, now, participants_json, len(messages)])

        # Insert new messages (skip duplicates)
        for msg in messages:
            attachments_json = json.dumps([a.model_dump() for a in msg.attachments])
            metadata_json = json.dumps(msg.metadata)
            try:
                self.conn.execute("""
                    INSERT OR IGNORE INTO messages
                    (uuid, parent_uuid, platform, session_id, role, subject_id, content, timestamp, attachments, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    msg.uuid,
                    msg.parent_uuid,
                    platform,
                    session_id,
                    msg.role,
                    msg.subject_id,
                    msg.content,
                    msg.timestamp,
                    attachments_json,
                    metadata_json,
                ])
            except Exception:
                # Skip duplicate
                pass

    def save_blob(
        self,
        platform: str,
        file_data: bytes,
        filename: str,
    ) -> str:
        """Save a blob file and return its hash.

        Args:
            platform: Platform name
            file_data: File content
            filename: Original filename

        Returns:
            SHA-256 hash of the file
        """
        file_hash = hashlib.sha256(file_data).hexdigest()
        ext = Path(filename).suffix.lstrip(".")

        # Create hierarchical path: <platform>/<hash[0:2]>/<hash[2:4]>/<hash>.<ext>
        blob_dir = self.blobs_dir / platform / file_hash[:2] / file_hash[2:4]
        blob_dir.mkdir(parents=True, exist_ok=True)

        blob_path = blob_dir / f"{file_hash}.{ext}"
        if not blob_path.exists():
            with open(blob_path, "wb") as f:
                f.write(file_data)

        return file_hash

    def list_conversations(
        self,
        platform: Optional[str] = None,
    ) -> list[ConversationSummary]:
        """List all conversations.

        Args:
            platform: Optional platform filter

        Returns:
            List of conversation summaries
        """
        if platform:
            rows = self.conn.execute("""
                SELECT session_id, platform, title, created_at, updated_at, message_count
                FROM conversations
                WHERE platform = ?
                ORDER BY updated_at DESC
            """, [platform]).fetchall()
        else:
            rows = self.conn.execute("""
                SELECT session_id, platform, title, created_at, updated_at, message_count
                FROM conversations
                ORDER BY updated_at DESC
            """).fetchall()

        results = []
        for row in rows:
            results.append(ConversationSummary(
                session_id=row[0],
                platform=row[1],
                title=row[2],
                created_at=row[3],
                updated_at=row[4],
                message_count=row[5],
            ))
        return results

    def get_messages(
        self,
        platform: Optional[str] = None,
        session_id: Optional[str] = None,
        role: Optional[str] = None,
        subject_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, list[Message]]:
        """Get messages with filtering and pagination.

        Args:
            platform: Optional platform filter
            session_id: Optional session ID filter
            role: Optional role filter (user/assistant)
            subject_id: Optional subject ID filter
            limit: Number of messages per page
            offset: Offset for pagination

        Returns:
            Tuple of (total_count, messages)
        """
        conditions = []
        params = []

        if platform is not None:
            conditions.append("platform = ?")
            params.append(platform)
        if session_id is not None:
            conditions.append("session_id = ?")
            params.append(session_id)
        if role is not None:
            conditions.append("role = ?")
            params.append(role)
        if subject_id is not None:
            conditions.append("subject_id = ?")
            params.append(subject_id)

        where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""

        # Get total count
        total = self.conn.execute(
            f"SELECT COUNT(*) FROM messages{where_clause}", params
        ).fetchone()[0]

        # Get paginated messages
        message_rows = self.conn.execute(
            f"""SELECT uuid, parent_uuid, role, subject_id, content, timestamp, attachments, metadata
            FROM messages{where_clause}
            ORDER BY timestamp ASC
            LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()

        from memory_talk.models import Attachment

        messages = []
        for msg_row in message_rows:
            attachments = json.loads(msg_row[6]) if msg_row[6] else []
            metadata = json.loads(msg_row[7]) if msg_row[7] else {}
            attachments_obj = [Attachment(**a) for a in attachments]

            messages.append(Message(
                uuid=msg_row[0],
                parent_uuid=msg_row[1],
                role=msg_row[2],
                subject_id=msg_row[3],
                content=msg_row[4],
                timestamp=msg_row[5],
                attachments=attachments_obj,
                metadata=metadata,
            ))

        return total, messages

    def search(self, query: str) -> list[SearchResult]:
        """Search conversations.

        Args:
            query: Search query

        Returns:
            List of matching messages with context
        """
        # Use LIKE for content search
        rows = self.conn.execute("""
            SELECT m.content, m.timestamp, c.session_id, c.platform, c.title
            FROM messages m
            JOIN conversations c ON m.session_id = c.session_id AND m.platform = c.platform
            WHERE LOWER(m.content) LIKE LOWER(?)
            ORDER BY m.timestamp DESC
        """, [f"%{query}%"]).fetchall()

        results = []
        for row in rows:
            results.append(SearchResult(
                session_id=row[2],
                platform=row[3],
                title=row[4],
                matched_message=row[0][:200],
                timestamp=row[1],
            ))
        return results

    def get_stats(self) -> tuple[int, int]:
        """Get total conversations and messages count.

        Returns:
            Tuple of (total_conversations, total_messages)
        """
        conv_count = self.conn.execute("""
            SELECT COUNT(*) FROM conversations
        """).fetchone()[0]

        msg_count = self.conn.execute("""
            SELECT COUNT(*) FROM messages
        """).fetchone()[0]

        return conv_count, msg_count

    def list_subjects(self) -> list[Subject]:
        """List all subjects.

        Returns:
            List of subjects
        """
        rows = self.conn.execute("""
            SELECT id, name, metadata, created_at, updated_at
            FROM subjects
            ORDER BY name ASC
        """).fetchall()

        results = []
        for row in rows:
            results.append(Subject(
                id=row[0],
                name=row[1],
                metadata=json.loads(row[2]) if row[2] else {},
                created_at=row[3],
                updated_at=row[4],
            ))
        return results

    def get_subject(self, subject_id: str) -> Optional[Subject]:
        """Get a subject by ID.

        Args:
            subject_id: Subject ID

        Returns:
            Subject or None if not found
        """
        row = self.conn.execute("""
            SELECT id, name, metadata, created_at, updated_at
            FROM subjects
            WHERE id = ?
        """, [subject_id]).fetchone()

        if not row:
            return None

        return Subject(
            id=row[0],
            name=row[1],
            metadata=json.loads(row[2]) if row[2] else {},
            created_at=row[3],
            updated_at=row[4],
        )

    def create_subject(self, subject: Subject) -> Subject:
        """Create a new subject.

        Args:
            subject: Subject to create

        Returns:
            Created subject
        """
        now = datetime.now()
        metadata_json = json.dumps(subject.metadata)

        self.conn.execute("""
            INSERT INTO subjects (id, name, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, [subject.id, subject.name, metadata_json, now, now])

        return Subject(
            id=subject.id,
            name=subject.name,
            metadata=subject.metadata,
            created_at=now,
            updated_at=now,
        )

    def update_subject(self, subject: Subject) -> Optional[Subject]:
        """Update an existing subject.

        Args:
            subject: Subject to update

        Returns:
            Updated subject or None if not found
        """
        existing = self.get_subject(subject.id)
        if not existing:
            return None

        now = datetime.now()
        metadata_json = json.dumps(subject.metadata)

        self.conn.execute("""
            UPDATE subjects
            SET name = ?, metadata = ?, updated_at = ?
            WHERE id = ?
        """, [subject.name, metadata_json, now, subject.id])

        return Subject(
            id=subject.id,
            name=subject.name,
            metadata=subject.metadata,
            created_at=existing.created_at,
            updated_at=now,
        )

    def delete_subject(self, subject_id: str) -> bool:
        """Delete a subject.

        Args:
            subject_id: Subject ID to delete

        Returns:
            True if deleted, False if not found
        """
        existing = self.get_subject(subject_id)
        if not existing:
            return False

        # Set subject_id to NULL for messages referencing this subject
        self.conn.execute("""
            UPDATE messages SET subject_id = NULL WHERE subject_id = ?
        """, [subject_id])

        # Delete the subject
        self.conn.execute("""
            DELETE FROM subjects WHERE id = ?
        """, [subject_id])

        return True
