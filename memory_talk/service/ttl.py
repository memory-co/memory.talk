"""TTL calculation — expires_at ↔ ttl conversion, factor-based refresh."""
from __future__ import annotations
import time
from memory_talk.config import TTLConfig

def compute_ttl(expires_at: float) -> int:
    return int(expires_at - time.time())

def initial_expires_at(cfg: TTLConfig) -> float:
    return time.time() + cfg.initial

def refresh_expires_at(current_expires_at: float, cfg: TTLConfig) -> float:
    remaining = max(current_expires_at - time.time(), 1)
    new_remaining = min(remaining * cfg.factor, cfg.max)
    return time.time() + new_remaining
