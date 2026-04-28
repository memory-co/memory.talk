"""util.ids — new_*_id() functions emit prefixed unique ULIDs."""
from __future__ import annotations

from memorytalk.util.ids import (
    CARD_PREFIX, LINK_PREFIX,
    new_card_id, new_event_id, new_link_id, new_search_id,
)


def test_new_card_id_has_prefix():
    cid = new_card_id()
    assert cid.startswith(CARD_PREFIX)
    assert len(cid) == len(CARD_PREFIX) + 26


def test_new_link_id_has_prefix():
    assert new_link_id().startswith(LINK_PREFIX)


def test_new_search_and_event_have_prefixes():
    assert new_search_id().startswith("sch_")
    assert new_event_id().startswith("evt_")


def test_ids_are_unique():
    ids = {new_card_id() for _ in range(1000)}
    assert len(ids) == 1000
