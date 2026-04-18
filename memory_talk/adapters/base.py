from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from memory_talk.models.session import Session

class Adapter(ABC):
    name: str
    @abstractmethod
    def discover(self) -> list[Path]: ...
    @abstractmethod
    def convert(self, source_path: Path) -> Session: ...
