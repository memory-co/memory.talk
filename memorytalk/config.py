"""Configuration — Settings model + Config with data-root layout and v1-residue detection."""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from pydantic import BaseModel


class ConfigValidationError(RuntimeError):
    """Raised by Config.validate() when the data root is not usable (e.g. v1 residue)."""


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
    endpoint: str | None = None
    auth_env_key: str | None = None
    dim: int = 384
    timeout: float = 30.0


class ServerConfig(BaseModel):
    port: int = 7788


class SearchConfig(BaseModel):
    default_top_k: int = 10
    comment_max_length: int = 500
    search_log_retention_days: int = 0


class Settings(BaseModel):
    server: ServerConfig = ServerConfig()
    vector: ProviderConfig = ProviderConfig(provider="lancedb")
    relation: ProviderConfig = ProviderConfig(provider="sqlite")
    embedding: EmbeddingConfig = EmbeddingConfig()
    ttl: TTLSettings = TTLSettings()
    search: SearchConfig = SearchConfig()


# Tables that only v1 used. If memory.db contains any of these, the data root
# belonged to v1 and we refuse to start (no auto-migration).
V1_ONLY_TABLES = frozenset({"recall_log", "card_tags", "session_tags"})


class Config:
    def __init__(self, data_root: Path | str | None = None):
        self.data_root = Path(data_root) if data_root else Path.home() / ".memory-talk"
        self._settings: Settings | None = None

    @property
    def settings(self) -> Settings:
        if self._settings is None:
            self._settings = self._load_settings()
        return self._settings

    @property
    def settings_path(self) -> Path:
        return self.data_root / "settings.json"

    @property
    def db_path(self) -> Path:
        return self.data_root / "memory.db"

    @property
    def vectors_dir(self) -> Path:
        return self.data_root / "vectors"

    @property
    def sessions_dir(self) -> Path:
        return self.data_root / "sessions"

    @property
    def cards_dir(self) -> Path:
        return self.data_root / "cards"

    @property
    def links_dir(self) -> Path:
        return self.data_root / "links"

    @property
    def logs_dir(self) -> Path:
        return self.data_root / "logs"

    @property
    def search_log_dir(self) -> Path:
        return self.logs_dir / "search"

    @property
    def pid_path(self) -> Path:
        return self.data_root / "server.pid"

    def ensure_dirs(self) -> None:
        for d in [
            self.data_root, self.vectors_dir, self.sessions_dir,
            self.cards_dir, self.links_dir, self.search_log_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    def validate(self) -> None:
        """Check data root is usable. Raises ConfigValidationError on v1 residue."""
        if not self.db_path.exists():
            return
        try:
            conn = sqlite3.connect(str(self.db_path))
            try:
                rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
                names = {r[0] for r in rows}
            finally:
                conn.close()
        except sqlite3.DatabaseError as e:
            raise ConfigValidationError(
                f"data root {self.data_root} has an unreadable memory.db: {e}"
            ) from e
        residue = names & V1_ONLY_TABLES
        if residue:
            raise ConfigValidationError(
                f"data root {self.data_root} contains v1 tables "
                f"{sorted(residue)} — v2 refuses to start against a v1 data root. "
                "Move or remove the old data root (no auto-migration)."
            )

    def save(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(
            json.dumps(self.settings.model_dump(), indent=2, ensure_ascii=False)
        )

    def _load_settings(self) -> Settings:
        if self.settings_path.exists():
            data = json.loads(self.settings_path.read_text())
            return Settings(**data)
        return Settings()
