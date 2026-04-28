"""util.ids — prefix_session_id(): adds sess_ prefix; idempotent on already-prefixed input."""
from __future__ import annotations

from memorytalk.util.ids import SESSION_PREFIX, prefix_session_id


def test_prefix_session_id_adds_prefix():
    assert prefix_session_id("187c6576-875f").startswith(SESSION_PREFIX)


def test_prefix_session_id_is_idempotent():
    already = "sess_187c6576-875f"
    assert prefix_session_id(already) == already
