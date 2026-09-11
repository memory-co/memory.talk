"""LocalFS -- FileSystemProvider primitives. See README.md."""
import pytest

from memorytalk.backend.providers import LocalFS


@pytest.fixture
def fs(tmp_path):
    return LocalFS(tmp_path / "root")


def test_write_then_read_roundtrips_bytes(fs):
    fs.write("a/b.txt", b"hello")
    assert fs.read("a/b.txt") == b"hello"


def test_write_replaces_whole_content(fs):
    fs.write("x", b"old-longer")
    fs.write("x", b"new")
    assert fs.read("x") == b"new"


def test_append_adds_to_end(fs):
    fs.append("log", b"1\n")
    fs.append("log", b"2\n")
    assert fs.read("log") == b"1\n2\n"


def test_read_missing_is_none_not_error(fs):
    assert fs.read("nope") is None
    assert fs.exists("nope") is False


def test_delete_is_idempotent(fs):
    fs.write("x", b"1")
    fs.delete("x")
    fs.delete("x")
    assert fs.exists("x") is False


def test_list_returns_all_files_under_prefix(fs):
    fs.write("w/a/1.json", b"{}")
    fs.write("w/b/2.json", b"{}")
    fs.write("other/3.json", b"{}")
    assert fs.list("w") == ["w/a/1.json", "w/b/2.json"]
    assert fs.list("missing") == []


def test_stat_reports_size(fs):
    fs.write("x", b"12345")
    assert fs.stat("x").size == 5
    assert fs.stat("nope") is None


def test_local_path_is_a_declared_capability(fs):
    assert fs.has("local_path") and fs.family == "fs"
    fs.write("a.txt", b"x")
    assert fs.local_path("a.txt").read_bytes() == b"x"


def test_path_escaping_root_is_rejected(fs):
    with pytest.raises(ValueError):
        fs.read("../outside")
