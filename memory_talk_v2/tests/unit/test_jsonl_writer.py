import json
from datetime import datetime, timezone

from memory_talk_v2.storage.jsonl_writer import DatedJsonlWriter


def test_creates_file_for_utc_date(tmp_path):
    base = tmp_path / "logs"
    w = DatedJsonlWriter(base)
    w.append({"k": "v"}, now=datetime(2026, 4, 22, 14, 30, tzinfo=timezone.utc))
    p = base / "2026-04-22.jsonl"
    assert p.exists()
    assert json.loads(p.read_text().strip()) == {"k": "v"}


def test_multiple_records_same_day(tmp_path):
    base = tmp_path / "logs"
    w = DatedJsonlWriter(base)
    d = datetime(2026, 4, 22, 14, 30, tzinfo=timezone.utc)
    w.append({"a": 1}, now=d)
    w.append({"b": 2}, now=d)
    lines = (base / "2026-04-22.jsonl").read_text().strip().split("\n")
    assert [json.loads(l) for l in lines] == [{"a": 1}, {"b": 2}]


def test_splits_by_utc_day(tmp_path):
    base = tmp_path / "logs"
    w = DatedJsonlWriter(base)
    w.append({"k": "x"}, now=datetime(2026, 4, 22, 23, 59, 59, tzinfo=timezone.utc))
    w.append({"k": "y"}, now=datetime(2026, 4, 23, 0, 0, 0, tzinfo=timezone.utc))
    assert (base / "2026-04-22.jsonl").exists()
    assert (base / "2026-04-23.jsonl").exists()


def test_iter_files_sorted(tmp_path):
    base = tmp_path / "logs"
    base.mkdir()
    for d in ["2026-04-21", "2026-04-20", "2026-04-22"]:
        (base / f"{d}.jsonl").write_text("")
    w = DatedJsonlWriter(base)
    assert [f.name for f in w.iter_files()] == [
        "2026-04-20.jsonl", "2026-04-21.jsonl", "2026-04-22.jsonl",
    ]


def test_ensure_ascii_false(tmp_path):
    base = tmp_path / "logs"
    w = DatedJsonlWriter(base)
    w.append({"query": "向量选型"}, now=datetime(2026, 4, 22, 0, 0, 0, tzinfo=timezone.utc))
    text = (base / "2026-04-22.jsonl").read_text()
    assert "向量选型" in text
