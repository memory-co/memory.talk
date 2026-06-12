"""memorytalk.migrations — schema-evolution content (peer to ``schemas/``).

Each subpackage ``vN/`` holds one version's snapshot + delta files for
all subsystems (currently ``database`` for SQLite and ``searchbase``
for LanceDB):

    vN/
      init_database.py     full-schema snapshot at vN (fresh installs)
      init_searchbase.py
      up_database.py       delta from v(N-1) to vN (upgrades)
      up_searchbase.py

The runner in :mod:`memorytalk.migration` discovers + applies these. See
``docs/works/v3/migration.md`` for the design.
"""
