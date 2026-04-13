"""Abstract base for platform adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from memory_talk.models import Session


class Adapter(ABC):
    """Converts platform-specific conversation format to standard Session."""

    name: str

    @abstractmethod
    def discover(self) -> list[Path]:
        """List all session files on this platform."""
        ...

    @abstractmethod
    def convert(self, source_path: Path) -> Session:
        """Convert a single platform file to a standard Session."""
        ...
