import pytest
from memory_talk.v2.ids import (
    new_card_id, new_session_id, new_link_id,
    prefix_session_id, parse_id, IdKind, InvalidIdError,
)


def test_new_card_id_has_prefix():
    cid = new_card_id()
    assert cid.startswith("card_")
    assert len(cid) == len("card_") + 26  # ULID is 26 chars


def test_new_link_id_has_prefix():
    assert new_link_id().startswith("link_")


def test_new_session_id_from_platform_id():
    assert prefix_session_id("187c6576-875f") == "sess_187c6576-875f"


def test_prefix_session_id_is_idempotent():
    already = "sess_187c6576-875f"
    assert prefix_session_id(already) == already


def test_parse_id_card():
    assert parse_id("card_01jz8k2m0000000000000000") == (IdKind.CARD, "01jz8k2m0000000000000000")


def test_parse_id_session():
    assert parse_id("sess_abc123") == (IdKind.SESSION, "abc123")


def test_parse_id_link():
    assert parse_id("link_01jzq7rm0000000000000000") == (IdKind.LINK, "01jzq7rm0000000000000000")


def test_parse_id_invalid_prefix():
    with pytest.raises(InvalidIdError):
        parse_id("sch_xxx")


def test_parse_id_no_prefix():
    with pytest.raises(InvalidIdError):
        parse_id("01jz8k2m")
