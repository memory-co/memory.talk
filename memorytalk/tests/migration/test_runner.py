"""MigrationRunner — mode selection + ordered application.

These tests build a synthetic ``migrations`` package on disk under
``tmp_path`` and point the runner at it, so the production v1
content stays out of the picture. Two stub versions (``v1``, ``v2``),
each with init/up files for both subsystems, all appending to a
single shared recorder so call order is observable.
"""
from __future__ import annotations

import importlib
import sys

import aiosqlite
import pytest


# ─── stub fixture ──────────────────────────────────────────────────


def _install_stub_migrations(root_dir, name: str) -> None:
    """Create a synthetic migrations package laid out like the real
    one: ``<name>/v{1,2}/{init,up}_{database,searchbase}.py``. The
    package's ``__init__`` exposes a list ``recorder`` that each
    method module appends to when its ``run()`` is awaited."""
    pkg_dir = root_dir / name
    pkg_dir.mkdir()
    # The shared recorder lives on the root package — every method
    # module imports it so call order is observable across files.
    (pkg_dir / "__init__.py").write_text("recorder = []\n")
    template = (
        f"from {name} import recorder\n"
        "async def run(handle):\n"
        "    recorder.append({tag!r})\n"
    )
    for version in ("v1", "v2"):
        vdir = pkg_dir / version
        vdir.mkdir()
        (vdir / "__init__.py").write_text("")
        for method in ("init", "up"):
            for sub in ("database", "searchbase"):
                tag = f"{version}/{method}_{sub}"
                (vdir / f"{method}_{sub}.py").write_text(
                    template.format(tag=tag)
                )


@pytest.fixture
def stub_pkg(tmp_path):
    """Yields ``(pkg_name, recorder)``. The recorder is reset between
    tests by virtue of the per-test tmp_path + sys.modules cleanup."""
    name = "memorytalk_test_migrations_stub"
    _install_stub_migrations(tmp_path, name)
    sys.path.insert(0, str(tmp_path))
    pkg = importlib.import_module(name)
    yield name, pkg.recorder
    sys.path.remove(str(tmp_path))
    for key in list(sys.modules):
        if key == name or key.startswith(name + "."):
            del sys.modules[key]


class _FakeAdmin:
    """No-op AdminBackend stand-in — only the runner's ``is not None``
    check cares about its identity here."""


# ─── tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fresh_install_runs_only_init_latest(tmp_path, stub_pkg):
    """No state + no tables + no data files → init_latest. Only the
    latest version's init runs."""
    from memorytalk.migration import MigrationRunner

    pkg, recorder = stub_pkg
    conn = await aiosqlite.connect(":memory:")
    runner = MigrationRunner(
        db_conn=conn, admin=_FakeAdmin(),
        state_path=tmp_path / "state.json",
        data_root=tmp_path / "no_such_dir",
        migrations_pkg=pkg,
    )
    summary = await runner.run()
    assert summary.mode == "init_latest"
    assert recorder == ["v2/init_database", "v2/init_searchbase"]

    # Re-running is a true no-op — both subs are marked for both
    # versions, so catch_up has nothing to apply.
    summary2 = await runner.run()
    assert summary2.mode == "catch_up"
    assert summary2.applied == []
    await conn.close()


@pytest.mark.asyncio
async def test_upgrade_from_zero_runs_all_ups(tmp_path, stub_pkg):
    """No state + pre-existing tables → upgrade_from_zero. Every
    version's up runs, in order, for every subsystem."""
    from memorytalk.migration import MigrationRunner

    pkg, recorder = stub_pkg
    conn = await aiosqlite.connect(":memory:")
    await conn.execute("CREATE TABLE legacy_marker (x INT)")
    await conn.commit()

    runner = MigrationRunner(
        db_conn=conn, admin=_FakeAdmin(),
        state_path=tmp_path / "state.json",
        data_root=tmp_path,
        migrations_pkg=pkg,
    )
    summary = await runner.run()
    assert summary.mode == "upgrade_from_zero"
    # Runner iterates per subsystem: all of database first, then all
    # of searchbase. Within each subsystem, version order.
    assert recorder == [
        "v1/up_database", "v2/up_database",
        "v1/up_searchbase", "v2/up_searchbase",
    ]
    await conn.close()


@pytest.mark.asyncio
async def test_catch_up_only_runs_pending(tmp_path, stub_pkg):
    """State already records v1 for both subs → catch_up runs only
    v2's up for each."""
    from memorytalk.migration import MigrationRunner

    pkg, recorder = stub_pkg
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"schema_version": 1, "applied": ['
        '{"version": "v1", "subsystem": "database", "method": "up",'
        ' "applied_at": "t", "duration_ms": 0},'
        '{"version": "v1", "subsystem": "searchbase", "method": "up",'
        ' "applied_at": "t", "duration_ms": 0}'
        ']}'
    )
    conn = await aiosqlite.connect(":memory:")
    runner = MigrationRunner(
        db_conn=conn, admin=_FakeAdmin(),
        state_path=state_path,
        data_root=tmp_path,
        migrations_pkg=pkg,
    )
    summary = await runner.run()
    assert summary.mode == "catch_up"
    assert recorder == ["v2/up_database", "v2/up_searchbase"]
    await conn.close()


@pytest.mark.asyncio
async def test_missing_admin_skips_searchbase(tmp_path, stub_pkg):
    """admin=None (searchbase backend failed to open) → runner only
    runs the database side; searchbase is left for a later boot."""
    from memorytalk.migration import MigrationRunner

    pkg, recorder = stub_pkg
    conn = await aiosqlite.connect(":memory:")
    runner = MigrationRunner(
        db_conn=conn, admin=None,
        state_path=tmp_path / "state.json",
        data_root=tmp_path / "no_such_dir",
        migrations_pkg=pkg,
    )
    summary = await runner.run()
    assert summary.mode == "init_latest"
    assert recorder == ["v2/init_database"]
    await conn.close()


@pytest.mark.asyncio
async def test_state_saved_per_migration(tmp_path, stub_pkg, monkeypatch):
    """If one migration crashes, the previous successful ones must be
    durably recorded so the next boot resumes from the right spot."""
    from memorytalk.migration import MigrationRunner

    pkg, _recorder = stub_pkg

    failing = importlib.import_module(f"{pkg}.v2.up_database")

    async def boom(_handle):
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(failing, "run", boom)

    conn = await aiosqlite.connect(":memory:")
    await conn.execute("CREATE TABLE legacy_marker (x INT)")
    await conn.commit()

    state_path = tmp_path / "state.json"
    runner = MigrationRunner(
        db_conn=conn, admin=_FakeAdmin(),
        state_path=state_path,
        data_root=tmp_path,
        migrations_pkg=pkg,
    )
    with pytest.raises(RuntimeError):
        await runner.run()

    import json
    body = json.loads(state_path.read_text())
    applied = {(a["version"], a["subsystem"]) for a in body["applied"]}
    assert ("v1", "database") in applied
    assert ("v2", "database") not in applied
    # Searchbase loop never started — the runner iterates subs serially
    # and v2/database aborted the run before searchbase began.
    assert ("v1", "searchbase") not in applied
    await conn.close()
