"""Configuration — reads/writes ~/.memory-talk/settings.json."""
from __future__ import annotations
import json
from pathlib import Path
from pydantic import BaseModel

class TTLConfig(BaseModel):
    initial: int = 2592000
    factor: float = 2.0
    max: int = 31536000

class TTLSettings(BaseModel):
    card: TTLConfig = TTLConfig()
    link: TTLConfig = TTLConfig(initial=1209600, max=15768000)

class ProviderConfig(BaseModel):
    provider: str = "lancedb"

class EmbeddingConfig(BaseModel):
    provider: str = "dummy"
    model: str = "all-MiniLM-L6-v2"

class Settings(BaseModel):
    vector: ProviderConfig = ProviderConfig(provider="lancedb")
    relation: ProviderConfig = ProviderConfig(provider="sqlite")
    embedding: EmbeddingConfig = EmbeddingConfig()
    ttl: TTLSettings = TTLSettings()

class Config:
    def __init__(self, data_root: Path | str | None = None):
        self.data_root = Path(data_root) if data_root else Path.home() / ".memory-talk"
        self._settings: Settings | None = None

    @property
    def settings(self) -> Settings:
        if self._settings is None:
            self._settings = self._load()
        return self._settings

    @property
    def settings_path(self) -> Path:
        return self.data_root / "settings.json"

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
    def db_path(self) -> Path:
        return self.data_root / "data" / "relation.db"

    @property
    def pid_path(self) -> Path:
        return self.data_root / "server.pid"

    def ensure_dirs(self) -> None:
        for d in [self.sessions_dir, self.cards_dir, self.vectors_dir, self.db_path.parent]:
            d.mkdir(parents=True, exist_ok=True)

    def _load(self) -> Settings:
        if self.settings_path.exists():
            data = json.loads(self.settings_path.read_text())
            return Settings(**data)
        return Settings()

    def save(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(json.dumps(self.settings.model_dump(), indent=2))
