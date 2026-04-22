"""Dated jsonl writer for v2 audit logs (search, events)."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


class DatedJsonlWriter:
    """Append-only jsonl writer that rotates files daily by UTC date.

    Layout: `<base_dir>/<YYYY-MM-DD>.jsonl`, one file per UTC day.
    """

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)

    def _file_for(self, now: datetime) -> Path:
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        else:
            now = now.astimezone(timezone.utc)
        return self.base_dir / f"{now.strftime('%Y-%m-%d')}.jsonl"

    def append(self, record: dict, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        path = self._file_for(now)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False))
            f.write("\n")

    def iter_files(self) -> Iterator[Path]:
        """Yield jsonl files in chronological order (sorted by filename)."""
        if not self.base_dir.exists():
            return
        for p in sorted(self.base_dir.glob("*.jsonl")):
            yield p
