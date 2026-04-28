"""Platform adapters for CLI `sync`."""
from memory_talk_v2.adapters.base import BaseAdapter, ADAPTERS, get_adapter, register  # noqa: F401
# Importing concrete adapters triggers @register side effects.
from memory_talk_v2.adapters import claude_code  # noqa: F401
