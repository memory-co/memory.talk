import json
from datetime import datetime, timezone
from memory_talk.v2.logging import DatedJsonlWriter


def test_writer_creates_file_for_today(tmp_path):
    base = tmp_path / "logs" / "search"
    w = DatedJsonlWriter(base_dir=base)
    w.append({"search_id": "sch_a", "query": "x"}, now=datetime(2026, 4, 22, 14, 30, tzinfo=timezone.utc))
    assert (base / "2026-04-22.jsonl").exists()
    line = (base / "2026-04-22.jsonl").read_text().strip()
    assert json.loads(line) == {"search_id": "sch_a", "query": "x"}


def test_writer_appends_multiple_lines_same_day(tmp_path):
    base = tmp_path / "logs" / "search"
    w = DatedJsonlWriter(base_dir=base)
    d = datetime(2026, 4, 22, 14, 30, tzinfo=timezone.utc)
    w.append({"a": 1}, now=d)
    w.append({"b": 2}, now=d)
    content = (base / "2026-04-22.jsonl").read_text().strip().split("\n")
    assert [json.loads(l) for l in content] == [{"a": 1}, {"b": 2}]


def test_writer_splits_by_utc_day(tmp_path):
    base = tmp_path / "logs" / "events"
    w = DatedJsonlWriter(base_dir=base)
    w.append({"k": "x"}, now=datetime(2026, 4, 22, 23, 59, 59, tzinfo=timezone.utc))
    w.append({"k": "y"}, now=datetime(2026, 4, 23, 0, 0, 0, tzinfo=timezone.utc))
    assert (base / "2026-04-22.jsonl").exists()
    assert (base / "2026-04-23.jsonl").exists()


def test_writer_iter_files_sorted(tmp_path):
    base = tmp_path / "logs" / "events"
    w = DatedJsonlWriter(base_dir=base)
    for d in ["2026-04-21", "2026-04-20", "2026-04-22"]:
        (base / f"{d}.jsonl").parent.mkdir(parents=True, exist_ok=True)
        (base / f"{d}.jsonl").write_text("")
    files = list(w.iter_files())
    assert [f.name for f in files] == ["2026-04-20.jsonl", "2026-04-21.jsonl", "2026-04-22.jsonl"]


def test_writer_creates_base_dir_if_missing(tmp_path):
    base = tmp_path / "new" / "nested" / "dir"
    w = DatedJsonlWriter(base_dir=base)
    w.append({"x": 1})
    assert base.exists()
