"""Repository layer — owns the aiosqlite connection + per-noun stores."""
from memorytalk.repository.store import SQLiteStore

__all__ = ["SQLiteStore"]
