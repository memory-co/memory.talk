"""Storage implementation for memory-talk."""
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from memory_talk.models import (
    ConversationMetadata,
    ConversationSummary,
    Message,
    SearchResult,
)


class Storage:
    """Storage engine for conversation data."""

    def __init__(self, base_path: Optional[Path] = None):
        """Initialize storage.

        Args:
            base_path: Base directory for storing data. Defaults to ~/.talk-memory/
        """
        if base_path is None:
            base_path = Path.home() / ".talk-memory"
        self.base_path = base_path
        self.conversations_dir = base_path / "conversations"
        self.blobs_dir = base_path / "blobs"
        self._ensure_directories()

    def _ensure_directories(self):
        """Ensure storage directories exist."""
        self.conversations_dir.mkdir(parents=True, exist_ok=True)
        self.blobs_dir.mkdir(parents=True, exist_ok=True)

    def _get_conversation_dir(self, platform: str, session_id: str) -> Path:
        """Get the directory for a conversation."""
        return self.conversations_dir / platform / session_id

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
        conv_dir = self._get_conversation_dir(platform, session_id)
        conv_dir.mkdir(parents=True, exist_ok=True)

        meta_path = conv_dir / "meta.yaml"
        messages_path = conv_dir / "messages.jsonl"

        # Build metadata
        now = metadata.get("created_at", messages[0].timestamp if messages else None)
        if isinstance(now, str):
            now = datetime.fromisoformat(now.replace("Z", "+00:00"))

        title = metadata.get("title", f"Conversation {session_id}")
        participants = metadata.get("participants", [])

        meta = ConversationMetadata(
            session_id=session_id,
            platform=platform,
            title=title,
            created_at=now,
            updated_at=now,
            participants=participants,
            message_count=len(messages),
        )

        # Save metadata
        with open(meta_path, "w") as f:
            yaml.dump(meta.model_dump(mode="json"), f)

        # Load existing messages for deduplication
        existing_uuids = set()
        if messages_path.exists():
            with open(messages_path) as f:
                for line in f:
                    msg = json.loads(line)
                    existing_uuids.add(msg.get("uuid"))

        # Save messages (deduplicate by uuid)
        with open(messages_path, "a") as f:
            for msg in messages:
                if msg.uuid not in existing_uuids:
                    f.write(msg.model_dump_json() + "\n")
                    existing_uuids.add(msg.uuid)

        # Update message count in metadata
        meta.message_count = len(existing_uuids)
        with open(meta_path, "w") as f:
            yaml.dump(meta.model_dump(mode="json"), f)

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
        results = []

        base = self.conversations_dir if platform is None else self.conversations_dir / platform

        if not base.exists():
            return results

        for platform_dir in [base] if platform else base.iterdir():
            if not platform_dir.is_dir():
                continue
            platform_name = platform_dir.name

            for session_dir in platform_dir.iterdir():
                if not session_dir.is_dir():
                    continue

                meta_path = session_dir / "meta.yaml"
                if not meta_path.exists():
                    continue

                with open(meta_path) as f:
                    meta_dict = yaml.safe_load(f)

                results.append(ConversationSummary(
                    session_id=meta_dict.get("session_id", session_dir.name),
                    platform=platform_name,
                    title=meta_dict.get("title", ""),
                    created_at=meta_dict.get("created_at", ""),
                    updated_at=meta_dict.get("updated_at", ""),
                    message_count=meta_dict.get("message_count", 0),
                ))

        return sorted(results, key=lambda x: x.updated_at, reverse=True)

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
        conv_dir = self._get_conversation_dir(platform, session_id)
        meta_path = conv_dir / "meta.yaml"
        messages_path = conv_dir / "messages.jsonl"

        if not meta_path.exists():
            return None

        with open(meta_path) as f:
            meta_dict = yaml.safe_load(f)

        messages = []
        if messages_path.exists():
            with open(messages_path) as f:
                for line in f:
                    messages.append(Message.model_validate_json(line))

        meta = ConversationMetadata(**meta_dict)
        return meta, messages

    def search(self, query: str) -> list[SearchResult]:
        """Search conversations.

        Args:
            query: Search query

        Returns:
            List of matching messages with context
        """
        results = []

        if not self.conversations_dir.exists():
            return results

        for platform_dir in self.conversations_dir.iterdir():
            if not platform_dir.is_dir():
                continue

            for session_dir in platform_dir.iterdir():
                if not session_dir.is_dir():
                    continue

                meta_path = session_dir / "meta.yaml"
                messages_path = session_dir / "messages.jsonl"

                if not meta_path.exists():
                    continue

                with open(meta_path) as f:
                    meta_dict = yaml.safe_load(f)

                title = meta_dict.get("title", "")
                session_id = meta_dict.get("session_id", session_dir.name)
                platform = platform_dir.name

                if messages_path.exists():
                    with open(messages_path) as f:
                        for line in f:
                            msg = json.loads(line)
                            content = msg.get("content", "")
                            if query.lower() in content.lower():
                                results.append(SearchResult(
                                    session_id=session_id,
                                    platform=platform,
                                    title=title,
                                    matched_message=content[:200],
                                    timestamp=msg.get("timestamp", ""),
                                ))

        return sorted(results, key=lambda x: x.timestamp, reverse=True)

    def get_stats(self) -> tuple[int, int]:
        """Get total conversations and messages count.

        Returns:
            Tuple of (total_conversations, total_messages)
        """
        total_conversations = 0
        total_messages = 0

        if not self.conversations_dir.exists():
            return total_conversations, total_messages

        for platform_dir in self.conversations_dir.iterdir():
            if not platform_dir.is_dir():
                continue

            for session_dir in platform_dir.iterdir():
                if not session_dir.is_dir():
                    continue

                meta_path = session_dir / "meta.yaml"
                if not meta_path.exists():
                    continue

                with open(meta_path) as f:
                    meta_dict = yaml.safe_load(f)

                total_conversations += 1
                total_messages += meta_dict.get("message_count", 0)

        return total_conversations, total_messages
