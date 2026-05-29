"""Configuration — Settings model + Config with data-root layout.

v3 simplifications vs v2:
- **No TTL config** — sinking/floating dynamics are computed at search time
  from review/read/recall counters, not from per-object expires_at.
- **No links / tags** — those entities are gone.
- **`data_root` hardcoded** to ``~/.memory.talk`` (docs/cli/v3/setup.md).
  Override via ``MEMORY_TALK_DATA_ROOT`` env var stays as a test hook.
- **`ranking_formula`** is new — drives the sinking/floating sort.
"""
from __future__ import annotations
import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict


_DEFAULT_RANKING_FORMULA = (
    "relevance + 0.1 * (review_up - review_down) "
    "+ 0.02 * log(read_count + 1) - 0.005 * age_days"
)


class ConfigValidationError(RuntimeError):
    """Raised when the data root or settings.json is not usable."""


class ProviderConfig(BaseModel):
    provider: str = "lancedb"


class EmbeddingConfig(BaseModel):
    provider: str = "local"
    model: str = "all-MiniLM-L6-v2"
    # The literal API key. ``${VAR}`` references in settings.json are
    # rendered at disk-load time (see ``Config._load_settings``); by the
    # time the field is read off the model it's a literal.
    endpoint: str | None = None
    auth_key: str | None = None
    dim: int = 384
    timeout: float = 30.0
    # Max ``input`` length per embed request. DashScope OpenAI-compatible
    # caps at 10 (the rest silently 400). OpenAI proper allows 2048, local
    # ignores this (sentence-transformers handles batching internally).
    # We default low and let users raise it for endpoints they know are
    # generous — wrong-direction default loses data; high default with
    # auto-detect loses requests.
    batch_size: int = 10


class ServerConfig(BaseModel):
    port: int = 7788


class SearchConfig(BaseModel):
    default_top_k: int = 10
    search_log_retention_days: int = 0
    ranking_formula: str = _DEFAULT_RANKING_FORMULA
    # Per-hit display budget for ``hits[].text``. When the round text
    # contains any query token, we return a keyword-windowed snippet
    # roughly this long; otherwise we return the round's first
    # ``snippet_head_chars`` characters as a preview.
    snippet_head_chars: int = 100


class RecallConfig(BaseModel):
    default_top_k: int = 3


class EndpointConfig(BaseModel):
    """A single sync target. (source, location) is the unique identifier;
    label is for display, extras are adapter-specific (e.g. ``auth_key``
    for openclaw).

    ``location`` interpretation per adapter:
      - ``claude-code`` / ``codex``: filesystem path
      - ``openclaw``: HTTPS URL
    """
    model_config = ConfigDict(extra="allow")  # adapter-specific kwargs survive

    source: str
    location: str
    label: str | None = None
    auth_key: str | None = None  # adapter-specific; openclaw uses it


class SyncConfig(BaseModel):
    enabled: bool = False
    debounce_ms: int = 200
    # When None (default), the watcher auto-detects from registered
    # adapters whose DEFAULT_LOCATION exists on disk. Users only need
    # to populate this list to (a) opt-in HTTP-based endpoints like
    # openclaw, (b) add a non-default local location, or (c) pin a
    # specific subset for testing.
    endpoints: list[EndpointConfig] | None = None


class ExploreConfig(BaseModel):
    cwd: str = "~/.memory.talk/explore"
    auto_default_limit: int = 5


class IndexConfig(BaseModel):
    """Vector index write tuning (0.8.x — issue #4 §4.3 fix).

    Decouples LanceDB ``table.add()`` batch size from the embedder's
    per-request cap. Embedding still batches small (API limit); these
    knobs control how the embedded rows aggregate before they hit
    LanceDB, which directly drives fragment count and downstream fd
    pressure on search.
    """
    # Row count that triggers a synchronous flush. 500 is a balance
    # between fragment-count savings (50× fewer fragments than the
    # naive embedder-batch-sized writes at DashScope's 10-cap) and
    # search-visibility latency for newly-ingested rounds.
    lance_flush_rows: int = 500
    # Wall-clock interval for the background flusher — catches the
    # last partial batch when ingest is bursty then idle. 0 disables
    # the background tick (tests use this).
    lance_flush_interval_seconds: float = 30.0


class Settings(BaseModel):
    server: ServerConfig = ServerConfig()
    vector: ProviderConfig = ProviderConfig(provider="lancedb")
    relation: ProviderConfig = ProviderConfig(provider="sqlite")
    embedding: EmbeddingConfig = EmbeddingConfig()
    search: SearchConfig = SearchConfig()
    recall: RecallConfig = RecallConfig()
    sync: SyncConfig = SyncConfig()
    explore: ExploreConfig = ExploreConfig()
    index: IndexConfig = IndexConfig()


def _default_data_root() -> Path:
    """Default data root — ~/.memory.talk, with a test-friendly env override.

    The override is **intentionally not advertised** in user-facing docs
    (docs/cli/v3/setup.md says data root is hardcoded). It exists so tests
    can run multiple isolated installs in tmpdirs without touching $HOME.
    """
    env = os.environ.get("MEMORY_TALK_DATA_ROOT")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".memory.talk"


class Config:
    """Holder for data-root layout + lazy-loaded Settings."""

    def __init__(self, data_root: Path | str | None = None):
        if data_root is None:
            self.data_root = _default_data_root()
        else:
            self.data_root = Path(data_root).expanduser()
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
    def sync_db_path(self) -> Path:
        """Sync connector state — separate from the main memory DB so it
        can be wiped/restored independently and future remote ingest
        doesn't have to reach into business data."""
        return self.data_root / "sync.db"

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
    def logs_dir(self) -> Path:
        return self.data_root / "logs"

    @property
    def search_log_dir(self) -> Path:
        return self.logs_dir / "search"

    @property
    def server_log_path(self) -> Path:
        """Daemon's main rotated log (uvicorn + memorytalk app loggers)."""
        return self.logs_dir / "server.log"

    @property
    def sync_log_dir(self) -> Path:
        return self.logs_dir / "sync"

    @property
    def sync_watch_log_path(self) -> Path:
        """Watchdog event trail (file events received, ingest outcomes,
        backfill progress) — rotates independently of server.log so a
        chatty watcher doesn't crowd out request/error logs."""
        return self.sync_log_dir / "watch.log"

    @property
    def pid_path(self) -> Path:
        return self.data_root / "server.pid"

    @property
    def port_path(self) -> Path:
        # Sibling to server.pid; written by `server start`. Lets `server status`
        # discover the live port without parsing settings.json — so a broken
        # ${VAR} render in settings doesn't make a live server look dead.
        return self.data_root / "server.port"

    def ensure_dirs(self) -> None:
        for d in [
            self.data_root, self.vectors_dir, self.sessions_dir,
            self.cards_dir, self.logs_dir, self.search_log_dir,
            self.sync_log_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    def _load_settings(self) -> Settings:
        if not self.settings_path.exists():
            return Settings()
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ConfigValidationError(
                f"settings.json at {self.settings_path} is not valid JSON: {e}"
            ) from e

        # One-shot migration: the legacy sync_state.json held the on/off
        # flag separately. Fold it into settings.sync.enabled if the user
        # hasn't already configured it, then delete the legacy file.
        self._migrate_legacy_sync_state(data)

        # Render ${VAR} references against os.environ across the whole
        # settings dict. Rendering at the disk-load boundary (not at request
        # time in providers) keeps the active value visible from one place
        # and avoids cross-context mismatches between setup and server.
        from memorytalk.util.env_template import render_env_in_obj
        try:
            render_env_in_obj(data)
        except KeyError as e:
            raise ConfigValidationError(
                f"settings.json references env var ${{{e.args[0]}}} which is not set"
            ) from e
        try:
            return Settings(**data)
        except Exception as e:
            raise ConfigValidationError(
                f"settings.json at {self.settings_path} does not match schema: {e}"
            ) from e

    def _migrate_legacy_sync_state(self, settings_data: dict) -> None:
        """Pre-0.5 stored sync's on/off in ``sync_state.json``. If that file
        is still present and the current settings.json doesn't yet set
        ``sync.enabled``, fold the legacy value in and remove the old file.
        Mutates ``settings_data`` in place and writes back to disk."""
        legacy = self.data_root / "sync_state.json"
        if not legacy.exists():
            return
        sync_block = settings_data.get("sync") or {}
        if "enabled" in sync_block:
            # User has already configured the new field; treat legacy as
            # stale and just remove it.
            legacy.unlink(missing_ok=True)
            return
        try:
            legacy_enabled = bool(
                json.loads(legacy.read_text(encoding="utf-8")).get("enabled")
            )
        except Exception:
            legacy_enabled = False
        sync_block["enabled"] = legacy_enabled
        settings_data["sync"] = sync_block
        from memorytalk.util.settings_io import write_settings_atomic
        write_settings_atomic(self.settings_path, settings_data)
        legacy.unlink(missing_ok=True)
