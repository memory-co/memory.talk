"""v1 fresh-install: searchbase (LanceDB) collection snapshot.

Documents the v1 shape of every collection. On fresh installs the
``LocalSearchBackend.create`` constructor has already auto-created
the declared collections from :mod:`memorytalk.service.searchbase_schema`,
so :func:`run` here is effectively a no-op — :func:`AdminBackend.create_collection`
short-circuits when the table already exists. We still issue the
calls so the snapshot serves as documentation for "what does v1 look
like" without having to read service-layer constants.
"""
from __future__ import annotations

from memorytalk.searchbase import AdminBackend
from memorytalk.service.searchbase_schema import SCHEMAS


async def run(admin: AdminBackend) -> None:
    """Make sure every v1 collection exists with the declared shape."""
    for name, schema in SCHEMAS.items():
        await admin.create_collection(name, schema)
