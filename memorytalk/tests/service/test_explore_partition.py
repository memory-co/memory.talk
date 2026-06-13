"""explore prior/posterior partition: global sessions split by the frozen
divider_at, minus the explore's own driving sessions (cwd under dir_path)."""
from __future__ import annotations

from memorytalk.service.explores import partition


def test_splits_global_sessions_excluding_driving_set():
    sessions = [
        {"session_id": "s_prior", "cwd": "/work/a",
         "last_round_update_time": "2026-05-01T00:00:00Z"},
        {"session_id": "s_post", "cwd": "/work/b",
         "last_round_update_time": "2026-06-01T00:00:00Z"},
        {"session_id": "s_anchor", "cwd": "/work/c",
         "last_round_update_time": "2026-05-10T00:00:00Z"},  # == divider → prior
        {"session_id": "s_drive", "cwd": "/explore/E1/x",
         "last_round_update_time": "2026-05-15T00:00:00Z"},  # driving → excluded
    ]

    out = partition(sessions, divider_at="2026-05-10T00:00:00Z", dir_path="/explore/E1")

    assert [s["session_id"] for s in out["prior"]] == ["s_prior", "s_anchor"]
    assert [s["session_id"] for s in out["posterior"]] == ["s_post"]


def test_session_without_cwd_is_not_driving():
    sessions = [
        {"session_id": "s", "cwd": None,
         "last_round_update_time": "2026-05-01T00:00:00Z"},
    ]
    out = partition(sessions, divider_at="2026-05-10T00:00:00Z", dir_path="/explore/E1")
    assert [s["session_id"] for s in out["prior"]] == ["s"]
