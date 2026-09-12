"""basic -- one file in origin, one in issue, both visible in stack. See README.md."""
import pytest


@pytest.fixture
def repo(svc):
    r = svc.collections.repo
    r.commit("origin", "[origin] add a/a.yaml", {"a/a.yaml": b"a: 1\n"})
    r.commit("issue", "[issue] add a/b.yaml", {"a/b.yaml": b"b: 2\n"})
    return r


def test_stack_sees_both_files(repo):
    assert sorted(p for p in repo.tree() if p != "collections.json") == ["a/a.yaml", "a/b.yaml"]


def test_origin_branch_only_has_its_own_file(repo):
    assert [e.path for e in repo.git.ls_tree(repo.layer_ref("origin")) if e.path != "collections.json"] == ["a/a.yaml"]


def test_issue_branch_only_has_its_own_file(repo):
    assert [e.path for e in repo.git.ls_tree(repo.layer_ref("issue")) if e.path != "collections.json"] == ["a/b.yaml"]


def test_stack_reads_back_the_content(repo):
    assert (repo.read("a/a.yaml"), repo.read("a/b.yaml")) == (b"a: 1\n", b"b: 2\n")
