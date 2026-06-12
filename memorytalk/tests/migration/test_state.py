"""MigrationState — JSON file round-trip + edge cases."""
from __future__ import annotations

import json

import pytest

from memorytalk.migration.state import MigrationState, StateLoadError


def test_missing_file_loads_empty(tmp_path):
    s = MigrationState(tmp_path / "state.json")
    assert s.load() == []
    assert s.highest_applied("database", ["v1", "v2"]) is None
    assert s.is_applied("v1", "database") is False


def test_mark_then_save_round_trips(tmp_path):
    p = tmp_path / "state.json"
    s = MigrationState(p)
    s.load()
    s.mark("v1", "database", method="init", applied_at="2026-01-01T00:00:00Z",
           duration_ms=12)
    s.save()
    assert p.exists()
    body = json.loads(p.read_text())
    assert body["schema_version"] == 1
    assert len(body["applied"]) == 1
    row = body["applied"][0]
    assert row["version"] == "v1"
    assert row["subsystem"] == "database"
    assert row["method"] == "init"
    assert row["duration_ms"] == 12


def test_mark_replaces_same_version_subsystem(tmp_path):
    """An init_latest run may mark the same (version, sub) twice — the
    state should reflect the last write, not stack duplicates."""
    s = MigrationState(tmp_path / "state.json")
    s.load()
    s.mark("v1", "database", method="up", applied_at="t1", duration_ms=10)
    s.mark("v1", "database", method="init", applied_at="t2", duration_ms=0)
    s.save()
    body = json.loads((tmp_path / "state.json").read_text())
    assert len(body["applied"]) == 1
    assert body["applied"][0]["method"] == "init"


def test_highest_applied_picks_latest_in_order(tmp_path):
    s = MigrationState(tmp_path / "state.json")
    s.load()
    s.mark("v1", "database", method="init", applied_at="t", duration_ms=0)
    s.mark("v3", "database", method="up", applied_at="t", duration_ms=0)
    s.mark("v2", "database", method="up", applied_at="t", duration_ms=0)
    assert s.highest_applied("database", ["v1", "v2", "v3", "v4"]) == "v3"
    assert s.highest_applied("searchbase", ["v1", "v2"]) is None


def test_malformed_file_raises(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("not json")
    s = MigrationState(p)
    with pytest.raises(StateLoadError):
        s.load()


def test_malformed_applied_field_raises(tmp_path):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"schema_version": 1, "applied": "oops"}))
    s = MigrationState(p)
    with pytest.raises(StateLoadError):
        s.load()


def test_save_is_atomic(tmp_path):
    """The tmp file shouldn't survive a successful save (would mean we
    didn't replace it)."""
    p = tmp_path / "state.json"
    s = MigrationState(p)
    s.load()
    s.mark("v1", "database", method="init", applied_at="t", duration_ms=0)
    s.save()
    siblings = sorted(c.name for c in p.parent.iterdir())
    assert siblings == ["state.json"]
