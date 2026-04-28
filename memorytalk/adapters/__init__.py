"""Platform adapters for CLI `sync`."""
from memorytalk.adapters.base import BaseAdapter, ADAPTERS, get_adapter, register  # noqa: F401
# Importing concrete adapters triggers @register side effects.
from memorytalk.adapters import claude_code  # noqa: F401
