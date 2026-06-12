"""Discover migration version directories under ``memorytalk.migrations``.

The runner doesn't import migrations eagerly — they're imported lazily
when needed (``import_init`` / ``import_up``) so that a broken
migration in version N doesn't keep the runner from listing and
applying versions < N.
"""
from __future__ import annotations

import importlib
import pkgutil
import re


_VERSION_RE = re.compile(r"^v(\d+)$")


def discover_versions(package: str = "memorytalk.migrations") -> list[str]:
    """Return all ``vN`` subpackages under ``package``, sorted by N.

    Returns an empty list if the package doesn't exist (no migrations
    declared yet — fresh-install case before v1 lands)."""
    try:
        pkg = importlib.import_module(package)
    except ImportError:
        return []
    versions: list[tuple[int, str]] = []
    for info in pkgutil.iter_modules(pkg.__path__):
        if not info.ispkg:
            continue
        m = _VERSION_RE.match(info.name)
        if m:
            versions.append((int(m.group(1)), info.name))
    versions.sort()
    return [name for _, name in versions]


def import_migration_module(
    version: str, subsystem: str, method: str,
    *, package: str = "memorytalk.migrations",
):
    """Import e.g. ``memorytalk.migrations.v1.up_searchbase``. Returns
    the module so the caller can call ``await module.run(handle)``.

    ``method`` is ``"init"`` or ``"up"``.
    ``subsystem`` is ``"database"`` or ``"searchbase"``.
    """
    return importlib.import_module(
        f"{package}.{version}.{method}_{subsystem}",
    )
