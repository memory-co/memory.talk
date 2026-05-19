"""Source-platform adapters — produce ingest payloads from local files."""
from memorytalk.adapters.base import ADAPTERS, BaseAdapter, get_adapter, register
# Import for side-effect: registers the claude-code adapter into ADAPTERS.
from memorytalk.adapters import claude_code  # noqa: F401

__all__ = ["ADAPTERS", "BaseAdapter", "get_adapter", "register"]
