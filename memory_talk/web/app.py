"""Web application with Flink-like dashboard."""
from datetime import datetime
from typing import Optional

from memory_talk.models import SourceStatus


class SourceManager:
    """Manages all sync sources and their status."""

    def __init__(self):
        """Initialize the source manager."""
        self._sources: dict[str, SourceStatus] = {}
        self._load_sources()

    def _load_sources(self):
        """Load available sources from the sources directory."""
        try:
            from memory_talk.sources.manager import get_source_manager
            sm = get_source_manager()
            # Register all sources
            for source in sm.list_sources():
                self._sources[source.name] = SourceStatus(
                    name=source.name,
                    status="stopped",
                    messages_synced=0,
                    last_sync_time=None,
                    error_message=None,
                )
        except ImportError:
            pass  # sources module not available yet

    def get_all_status(self) -> list[SourceStatus]:
        """Get status of all sources.

        Returns:
            List of source statuses
        """
        return list(self._sources.values())

    def get_status(self, name: str) -> Optional[SourceStatus]:
        """Get status of a specific source.

        Args:
            name: Source name

        Returns:
            Source status or None if not found
        """
        return self._sources.get(name)

    def update_status(
        self,
        name: str,
        status: str,
        messages_synced: Optional[int] = None,
        error_message: Optional[str] = None,
    ):
        """Update source status.

        Args:
            name: Source name
            status: New status (running, stopped, error)
            messages_synced: Number of messages synced
            error_message: Error message if status is error
        """
        if name in self._sources:
            source = self._sources[name]
            source.status = status
            if messages_synced is not None:
                source.messages_synced = messages_synced
            if status == "running":
                source.last_sync_time = datetime.now()
            if error_message is not None:
                source.error_message = error_message
            self._sources[name] = source

    def register_source(self, name: str):
        """Register a new source.

        Args:
            name: Source name
        """
        if name not in self._sources:
            self._sources[name] = SourceStatus(
                name=name,
                status="stopped",
                messages_synced=0,
                last_sync_time=None,
                error_message=None,
            )
