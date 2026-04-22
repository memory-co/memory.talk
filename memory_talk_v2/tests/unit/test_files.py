from memory_talk_v2.storage import files as F


def test_session_dir_bucketing(tmp_path):
    d = F.session_dir(tmp_path, "claude-code", "sess_abc123")
    assert d == tmp_path / "claude-code" / "ab" / "sess_abc123"


def test_session_meta_and_rounds_roundtrip(tmp_path):
    F.write_session_meta(tmp_path, "claude-code", "sess_abc", {"session_id": "sess_abc", "tags": []})
    assert F.read_session_meta(tmp_path, "claude-code", "sess_abc")["session_id"] == "sess_abc"

    F.append_session_rounds(tmp_path, "claude-code", "sess_abc", [
        {"idx": 1, "round_id": "r1"}, {"idx": 2, "round_id": "r2"},
    ])
    F.append_session_rounds(tmp_path, "claude-code", "sess_abc", [
        {"idx": 3, "round_id": "r3"},
    ])
    rounds = F.read_session_rounds(tmp_path, "claude-code", "sess_abc")
    assert [r["idx"] for r in rounds] == [1, 2, 3]


def test_card_roundtrip(tmp_path):
    F.write_card(tmp_path, {"card_id": "card_xyz", "summary": "s", "rounds": []})
    assert F.read_card(tmp_path, "card_xyz")["summary"] == "s"
    cards = list(F.iter_cards(tmp_path))
    assert len(cards) == 1


def test_link_roundtrip(tmp_path):
    F.write_link(tmp_path, {"link_id": "link_xyz", "source_id": "card_a", "target_id": "sess_b"})
    assert F.read_link(tmp_path, "link_xyz")["source_id"] == "card_a"


def test_iter_session_dirs(tmp_path):
    F.write_session_meta(tmp_path, "claude-code", "sess_ab1", {})
    F.write_session_meta(tmp_path, "claude-code", "sess_cd2", {})
    dirs = list(F.iter_session_dirs(tmp_path))
    names = {d.name for d in dirs}
    assert names == {"sess_ab1", "sess_cd2"}
