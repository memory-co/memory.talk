"""Base class for sync sources."""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SourceConfig(BaseModel):
    """Configuration for a sync source."""
    name: str
    enabled: bool = True
    interval: int = 300  # seconds


class Source(ABC):
    """Abstract base class for sync sources."""

    def __init__(self, config: SourceConfig):
        """Initialize the source.

        Args:
            config: Source configuration
        """
        self.config = config
        self._messages_synced = 0
        self._last_sync_time: Optional[datetime] = None
        self._status = "stopped"
        self._error_message: Optional[str] = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the source name."""
        pass

    @property
    def status(self) -> str:
        """Return the current status."""
        return self._status

    @property
    def messages_synced(self) -> int:
        """Return the number of messages synced."""
        return self._messages_synced

    @property
    def last_sync_time(self) -> Optional[datetime]:
        """Return the last sync time."""
        return self._last_sync_time

    @property
    def error_message(self) -> Optional[str]:
        """Return the error message if any."""
        return self._error_message

    @abstractmethod
    def start(self):
        """Start the source sync."""
        pass

    @abstractmethod
    def stop(self):
        """Stop the source sync."""
        pass

    @abstractmethod
    def sync(self) -> int:
        """Perform a sync and return the number of messages synced.

        Returns:
            Number of messages synced
        """
        pass

    def _update_status(
        self,
        status: str,
        messages_synced: Optional[int] = None,
        error_message: Optional[str] = None,
    ):
        """Update the source status.

        Args:
            status: New status
            messages_synced: Number of messages synced
            error_message: Error message if any
        """
        self._status = status
        if messages_synced is not None:
            self._messages_synced = messages_synced
        if error_message is not None:
            self._error_message = error_message
        if status == "running":
            self._last_sync_time = datetime.now()
