"""Source-platform adapters — produce ingest payloads from upstream sources."""
from memorytalk.adapters.base import ADAPTERS, BaseAdapter, get_adapter, register
# Side-effect imports register each adapter into ADAPTERS. Keep this list
# of imports in sync with the supported source names users may put in
# ``settings.sync.endpoints``.
from memorytalk.adapters import claude_code  # noqa: F401
from memorytalk.adapters import codex        # noqa: F401
from memorytalk.adapters import openclaw     # noqa: F401

__all__ = ["ADAPTERS", "BaseAdapter", "get_adapter", "register"]
