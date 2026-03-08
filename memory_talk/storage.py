"""Storage implementation for memory-talk using DuckDB."""
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import duckdb

from memory_talk.models import (
    ConversationMetadata,
    ConversationSummary,
    Message,
    SearchResult,
)


class Storage:
    """Storage engine for conversation data using DuckDB."""

    def __init__(self, base_path: Optional[Path] = None):
        """Initialize storage.

        Args:
            base_path: Base directory for storing data. Defaults to ~/.talk-memory/
        """
        if base_path is None:
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

        # Create messages table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                uuid VARCHAR,
                parent_uuid VARCHAR,
                platform VARCHAR,
                session_id VARCHAR,
                role VARCHAR,
                content VARCHAR,
                timestamp TIMESTAMP,
                attachments JSON,
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
            try:
                self.conn.execute("""
                    INSERT OR IGNORE INTO messages
                    (uuid, parent_uuid, platform, session_id, role, content, timestamp, attachments)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    msg.uuid,
                    msg.parent_uuid,
                    platform,
                    session_id,
                    msg.role,
                    msg.content,
                    msg.timestamp,
                    attachments_json,
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

    def get_conversation(
        self,
        platform: str,
        session_id: str,
    ) -> Optional[tuple[ConversationMetadata, list[Message]]]:
        """Get a specific conversation.

        Args:
            platform: Platform name
            session_id: Session ID

        Returns:
            Tuple of (metadata, messages) or None if not found
        """
        # Get conversation metadata
        row = self.conn.execute("""
            SELECT session_id, platform, title, created_at, updated_at, participants, message_count
            FROM conversations
            WHERE session_id = ? AND platform = ?
        """, [session_id, platform]).fetchone()

        if not row:
            return None

        participants = json.loads(row[5]) if row[5] else []
        from memory_talk.models import Participant
        participants_obj = [Participant(**p) for p in participants]

        meta = ConversationMetadata(
            session_id=row[0],
            platform=row[1],
            title=row[2],
            created_at=row[3],
            updated_at=row[4],
            participants=participants_obj,
            message_count=row[6],
        )

        # Get messages
        message_rows = self.conn.execute("""
            SELECT uuid, parent_uuid, role, content, timestamp, attachments
            FROM messages
            WHERE session_id = ? AND platform = ?
            ORDER BY timestamp ASC
        """, [session_id, platform]).fetchall()

        messages = []
        for msg_row in message_rows:
            attachments = json.loads(msg_row[5]) if msg_row[5] else []
            from memory_talk.models import Attachment
            attachments_obj = [Attachment(**a) for a in attachments]

            messages.append(Message(
                uuid=msg_row[0],
                parent_uuid=msg_row[1],
                role=msg_row[2],
                content=msg_row[3],
                timestamp=msg_row[4],
                attachments=attachments_obj,
            ))

        return meta, messages

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
