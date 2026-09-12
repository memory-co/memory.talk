"""collections/issue_rules -- the issue directory validator. See README.md."""
import pytest

from tests._util import git_authors

IP = "memory.talk/配置/该走文件还是环境变量"
A = "positions/只用环境变量.md"


@pytest.fixture
def issue(client):
    client.post(f"/api/collections/issue/{IP}", json={"files": {"readme.md": "背景", A: "为什么"}})
    return IP


def _put(client, files, headers=None, **kw):
    return client.put(f"/api/collections/issue/{IP}", json={"files": files, **kw}, headers=headers)


def test_argument_is_an_appended_line(client, issue):
    r = _put(client, {A: "为什么\n\n## 论证\n- 试了一遍,够用(work_try#9)\n"})
    assert r.status_code == 200
    r = _put(client, {A: "为什么\n\n## 论证\n- 试了一遍,够用(work_try#9)\n- 本地开发要改十几个变量\n"})
    assert r.status_code == 200 and r.json()["files"][A].endswith("- 本地开发要改十几个变量\n")


def test_position_body_cannot_be_rewritten(client, issue):
    r = _put(client, {A: "改了主意"})
    assert r.status_code == 422 and "只增不改" in r.json()["message"]


def test_position_cannot_be_deleted_or_renamed(client, issue):
    r = _put(client, {A: None})
    assert r.status_code == 422 and "不能删" in r.json()["message"]
    r = _put(client, {A: None, "positions/换个说法.md": "为什么"})
    assert r.status_code == 422 and "positions/只用环境变量.md" in r.json()["message"]


def test_readme_cannot_be_deleted_but_can_change(client, issue):
    assert _put(client, {"readme.md": None}).status_code == 422
    assert _put(client, {"readme.md": "改了展开"}).json()["files"]["readme.md"] == "改了展开"


def test_only_the_three_kinds_of_files(client, issue):
    r = _put(client, {"notes.txt": "x"})
    assert r.status_code == 422 and "notes.txt" in r.json()["message"]
    assert _put(client, {"positions/.md": "空主张"}).status_code == 422


def test_meta_links_are_typed_and_unique(client, issue):
    ok = _put(client, {"meta.yaml": "links:\n- {type: specializes, target: memory.talk/更大的问题}\n"})
    assert ok.status_code == 200
    r = _put(client, {"meta.yaml": "links:\n- {type: nope, target: x}\n"})
    assert r.status_code == 422 and "meta.yaml" in r.json()["message"]
    r = _put(client, {"meta.yaml": "links:\n- {type: related, target: x}\n- {type: related, target: x}\n"})
    assert r.status_code == 422 and "重复" in r.json()["message"]


def test_meta_rank_must_name_existing_positions_and_no_extra_keys(client, issue):
    ok = _put(client, {"meta.yaml": "positions:\n- {claim: 只用环境变量, note: 够用}\nsummary: 先这样\n"})
    assert ok.status_code == 200
    r = _put(client, {"meta.yaml": "positions:\n- {claim: 没这个}\n"})
    assert r.status_code == 422 and "没这个" in r.json()["message"]
    r = _put(client, {"meta.yaml": "score: 1\n"})
    assert r.status_code == 422 and "score" in r.json()["message"]


def test_one_bad_file_rejects_the_whole_batch(client, svc, issue):
    r = _put(client, {"positions/乙.md": "b", "extra.txt": "x"})
    assert r.status_code == 422
    assert svc.collections.repo.read(f"{IP}.issue/positions/乙.md") is None


def test_who_and_when_live_in_git(client, H, issue):
    _put(client, {"positions/乙.md": "b"}, headers=H("alice"), subject=f"position {IP}: 乙")
    _put(client, {A: "为什么\n\n## 论证\n- 够用\n"}, headers=H("bob"), subject=f"argue {IP}#只用环境变量: 够用")
    assert git_authors(client, 2)[0::2] == ["bob", "alice"]
