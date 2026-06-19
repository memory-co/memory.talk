"""LocalAdminBackend — schema-level operations for the migration framework.

Wraps :class:`CollectionIndex` (which has the LanceDB connection) and
translates the generic :class:`AdminBackend` Protocol into LanceDB-
specific calls (``add_columns`` / ``alter_columns`` / ``drop_columns``,
plus table create / drop).

Lives in its own file so the public ``backend.py`` doesn't need to
know about migration concerns — ``backend.admin()`` returns a fresh
``LocalAdminBackend`` and the rest is opaque.
"""
from __future__ import annotations

from memorytalk.searchbase._types import AdminBackend
from memorytalk.searchbase.local.index import CollectionIndex
from memorytalk.searchbase.local.util import TYPE_TAGS


def _sql_literal_for_default(value: object | None) -> str:
    """Render a Python default as a LanceDB SQL literal for use in an
    ``add_columns`` transform expression."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    # string: single-quote with embedded quote doubling
    return "'" + str(value).replace("'", "''") + "'"


class LocalAdminBackend(AdminBackend):
    """:class:`AdminBackend` impl over a single :class:`CollectionIndex`.

    Constructed by ``LocalSearchBackend.admin()``. The migration runner
    holds it for the duration of one ``runner.run()`` call; lifetime
    coincides with the LocalSearchBackend's open connection.
    """

    def __init__(self, index: CollectionIndex):
        self._index = index

    # ─── discovery ─────────────────────────────────────────────────

    async def list_collections(self) -> list[str]:
        return await self._index._list_tables()

    async def list_columns(self, collection: str) -> list[str]:
        if not await self._index._exists(collection):
            return []
        table = await self._index.db.open_table(collection)
        schema = await table.schema()
        return [f.name for f in schema]

    # ─── column-level alter ────────────────────────────────────────

    async def add_column(
        self,
        collection: str,
        column: str,
        type_: str,
        *,
        default: object | None = None,
        sql_compute: str | None = None,
    ) -> None:
        """Add a column via LanceDB's ``add_columns`` transform API.

        ``sql_compute`` takes precedence; if absent, ``default`` is
        rendered as a SQL literal and used as the transform. If both
        are None, the column is added as NULL for all existing rows.

        ``type_`` is one of ``str / int / float / bool`` — the Arrow
        type is inferred at add-time, but LanceDB's add_columns infers
        from the SQL expression. To force a type we wrap with CAST.
        """
        if type_ not in TYPE_TAGS:
            raise ValueError(f"unknown type tag {type_!r}")

        # Build the SQL expression. Cast it so the resulting column has
        # the right Arrow type (LanceDB infers from expression type).
        cast_target = {
            "str": "STRING",
            "int": "BIGINT",
            "float": "DOUBLE",
            "bool": "BOOLEAN",
        }[type_]

        if sql_compute is not None:
            expr = f"CAST(({sql_compute}) AS {cast_target})"
        else:
            expr = f"CAST({_sql_literal_for_default(default)} AS {cast_target})"

        table = await self._index.db.open_table(collection)
        await table.add_columns({column: expr})
        # Invalidate the FTS-index memo for this collection — the
        # schema changed, future search may need to re-ensure.
        self._index._fts_index_known.discard(collection)

    async def rename_column(
        self, collection: str, old: str, new: str,
    ) -> None:
        table = await self._index.db.open_table(collection)
        await table.alter_columns({"path": old, "rename": new})
        self._index._fts_index_known.discard(collection)

    async def drop_column(self, collection: str, column: str) -> None:
        table = await self._index.db.open_table(collection)
        await table.drop_columns([column])
        self._index._fts_index_known.discard(collection)

    # ─── table-level ───────────────────────────────────────────────

    async def create_collection(self, name: str, schema: dict) -> None:
        """Create a table from a declared schema spec — same shape as
        ``CollectionIndex.create``'s ``collections`` arg entry:
        ``{"fields": {field: type_tag, ...}, "auto_split": bool}``.

        Adds the collection to the index's declared set so that
        subsequent ``_schema_for`` lookups know about it (matters when
        the migration runner creates a collection mid-flight)."""
        if await self._index._exists(name):
            return
        # Inject into declared so _schema_for works.
        self._index._declared[name] = dict(schema)
        if schema.get("auto_split"):
            self._index._auto_split.add(name)
        self._index._collections.add(name)
        arrow_schema = self._index._schema_for(name)
        await self._index.db.create_table(name, schema=arrow_schema)

    async def drop_collection(self, name: str) -> None:
        if not await self._index._exists(name):
            return
        await self._index.db.drop_table(name)
        self._index._collections.discard(name)
        self._index._declared.pop(name, None)
        self._index._auto_split.discard(name)
        self._index._fts_index_known.discard(name)

    async def rename_collection(self, old: str, new: str) -> None:
        """Rename a collection (data preserved). Idempotent: no-op once
        ``old`` is gone.

        ``new`` may already exist as an **empty placeholder** — boot
        eagerly creates every declared collection (see
        ``CollectionIndex.create``), so when a migration renames an
        on-disk ``old`` into a now-declared ``new`` the placeholder races
        ahead. We drop that empty placeholder so the rename — which
        carries ``old``'s real rows — can proceed. A **non-empty** ``new``
        is left untouched (no-op) to avoid clobbering real data.
        """
        tables = await self._index._list_tables()
        if old not in tables:
            return
        new_spec = None
        if new in tables:
            if await self._index.count(new) > 0:
                return  # real data under `new` — refuse to clobber
            new_spec = self._index._declared.get(new)
            await self.drop_collection(new)
        try:
            await self._index.db.rename_table(old, new)
        except (AttributeError, NotImplementedError):
            import os
            import lancedb
            try:
                await self._index.db.close()
            except Exception:
                pass
            os.rename(
                self._index.data_dir / f"{old}.lance",
                self._index.data_dir / f"{new}.lance",
            )
            self._index.db = await lancedb.connect_async(str(self._index.data_dir))
        # Mirror the bookkeeping that create/drop_collection maintain.
        self._index._collections.discard(old)
        self._index._collections.add(new)
        spec = self._index._declared.pop(old, None)
        if spec is not None:
            self._index._declared[new] = spec
        elif new_spec is not None:
            # `old` wasn't a declared collection (it's the legacy name);
            # keep `new`'s declared spec that the dropped placeholder held.
            self._index._declared.setdefault(new, new_spec)
        if old in self._index._auto_split:
            self._index._auto_split.discard(old)
            self._index._auto_split.add(new)
        self._index._fts_index_known.discard(old)
