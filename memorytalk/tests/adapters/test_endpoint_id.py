"""mint_session_id contract + endpoint isolation.

Two endpoints (same source, different ``location``) must produce
*different* canonical session_ids even from the same raw upstream id.
Two adapters from the same endpoint must produce *equal* ids — that's
how SyncWatcher's checkpoint lookups stay deterministic across restarts.
"""
from __future__ import annotations

from memorytalk.adapters.claude_code import ClaudeCodeAdapter
from memorytalk.adapters.codex import CodexAdapter


def test_same_endpoint_same_minted_id():
    a = ClaudeCodeAdapter(location="/home/u/.claude/projects")
    b = ClaudeCodeAdapter(location="/home/u/.claude/projects")
    raw = "01234567-89ab-cdef-0123-456789abcdef"
    assert a.mint_session_id(raw) == b.mint_session_id(raw)


def test_different_locations_yield_different_ids():
    """The point of including (source, location) in the loc-hash is to
    keep two endpoints' sessions distinct even when raw ids collide."""
    us = ClaudeCodeAdapter(location="/home/u/.claude/projects")
    eu = ClaudeCodeAdapter(location="/mnt/other/.claude/projects")
    raw = "01234567-89ab-cdef-0123-456789abcdef"
    sid_us = us.mint_session_id(raw)
    sid_eu = eu.mint_session_id(raw)
    assert sid_us != sid_eu
    # Last segment is shared (same raw id); loc-hash is the differentiator.
    assert sid_us.split("-")[-1] == sid_eu.split("-")[-1]


def test_different_sources_same_location_yield_different_ids():
    """source goes into the loc-hash too, so claude-code and codex
    pointed at the same physical path (contrived but legal) get
    different sids."""
    cc = ClaudeCodeAdapter(location="/tmp/shared")
    cx = CodexAdapter(location="/tmp/shared")
    raw = "01234567-89ab-cdef-0123-456789abcdef"
    assert cc.mint_session_id(raw) != cx.mint_session_id(raw)


def test_minted_id_shape():
    """Format: ``sess-<8-hex>-<lastseg>``. <lastseg> is the chunk after
    the final ``-`` in the raw id (git short-sha style)."""
    a = ClaudeCodeAdapter(location="/x")
    sid = a.mint_session_id("01234567-89ab-cdef-0123-456789abcdef")
    parts = sid.split("-")
    assert parts[0] == "sess"
    assert len(parts[1]) == 8           # loc hash
    assert parts[-1] == "456789abcdef"  # last raw segment


def test_loc_code_and_endpoint_id_derive_from_same_input():
    """``loc_code`` (sha256(source#location)[:8]) and ``endpoint_id``
    (``source#location``) are both computed from (source, location), so
    two equal-location adapters must produce equal values for both."""
    a = ClaudeCodeAdapter(location="/home/u/.claude/projects")
    b = ClaudeCodeAdapter(location="/home/u/.claude/projects")
    assert a.loc_code == b.loc_code
    assert a.endpoint_id == b.endpoint_id
    c = ClaudeCodeAdapter(location="/mnt/other/.claude/projects")
    assert a.loc_code != c.loc_code
    assert a.endpoint_id != c.endpoint_id
