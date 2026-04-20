"""CLI dispatcher. Selects a version via MEMORY_TALK_CLI_VERSION env var."""
from __future__ import annotations
import importlib
import os

_version = os.environ.get("MEMORY_TALK_CLI_VERSION", "v1")
_module = importlib.import_module(f"memory_talk.cli.{_version}")

globals().update({k: getattr(_module, k) for k in _module.__all__})
__all__ = list(_module.__all__)
