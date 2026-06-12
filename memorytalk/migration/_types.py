"""Value types for the migration runner."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Mode = Literal["init_latest", "upgrade_from_zero", "catch_up"]
Subsystem = Literal["database", "searchbase"]


@dataclass
class Summary:
    """What the runner did on this invocation. Returned by
    :meth:`MigrationRunner.run`; useful for log lines + tests."""

    mode: Mode
    applied: list[tuple[str, Subsystem]] = field(default_factory=list)
    skipped: list[tuple[str, Subsystem]] = field(default_factory=list)

    @property
    def applied_count(self) -> int:
        return len(self.applied)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)
