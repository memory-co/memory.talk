"""Configuration management for memory.talk."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class Config(BaseModel):
    data_root: Path = Path.home() / ".memory-talk"
    vector_backend: str = "lancedb"
    relation_backend: str = "sqlite"
    embedding_backend: str = "local"
    embedding_model: str = "all-MiniLM-L6-v2"

    @property
    def sessions_dir(self) -> Path:
        return self.data_root / "sessions"

    @property
    def cards_dir(self) -> Path:
        return self.data_root / "cards"

    @property
    def vectors_dir(self) -> Path:
        return self.data_root / "data" / "vectors"

    @property
    def relation_db_path(self) -> Path:
        return self.data_root / "data" / "relation.db"

    @property
    def config_path(self) -> Path:
        return self.data_root / "config.yaml"

    def save(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        data = self.model_dump(mode="json")
        data["data_root"] = str(data["data_root"])
        with open(self.config_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)

    @classmethod
    def load(cls, data_root: Path | str | None = None) -> Config:
        root = Path(data_root) if data_root else (Path.home() / ".memory-talk")
        config_path = root / "config.yaml"
        if config_path.exists():
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}
            data["data_root"] = root
            return cls(**data)
        return cls(data_root=root)
