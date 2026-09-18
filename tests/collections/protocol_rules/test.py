"""collections/protocol_rules -- the engine checks each protocol rule. See README.md."""
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


def test_paths_must_match_one_kind_of_file(client, issue):
    r = _put(client, {"notes.txt": "x"})
    assert r.status_code == 422 and "notes.txt" in r.json()["message"] and "positions/{name}.md" in r.json()["message"]
    assert _put(client, {"positions/深/一层.md": "x"}).status_code == 422                     # name 不能含 /


def test_required_file_cannot_be_deleted_but_others_can(client, issue):
    assert "不能删" in _put(client, {"readme.md": None}).json()["message"]
    assert _put(client, {A: None}).status_code == 200


def test_fields_are_validated_by_type(client, issue):
    ok = _put(client, {"readme.md": "---\nlinks:\n- {type: specializes, target: memory.talk/更大的问题}\nsummary: 先这样\n---\n\n背景"})
    assert ok.status_code == 200
    bad = lambda files: _put(client, files).json()["message"]
    assert "只能是" in bad({"readme.md": "---\nlinks:\n- {type: nope, target: x}\n---\n"})               # enum
    assert "必填" in bad({"readme.md": "---\nlinks:\n- {type: related}\n---\n"})                          # object 里 required 的键
    assert "要是数字" in bad({A: "---\nrank: 第一\n---\n\n为什么"})                                        # number
    assert "不认识的字段" in bad({A: "---\nscore: 1\n---\n\n为什么"})                                       # 未声明的键
    assert "要是列表" in bad({"readme.md": "---\nlinks: {type: related, target: x}\n---\n"})              # list
    assert _put(client, {A: "---\nrank: 1\nverdict: 够用\nlinks:\n- {type: supports, target: memory.talk/x}\n---\n\n为什么"}).status_code == 200


def test_frontmatter_must_be_a_mapping(client, issue):
    r = _put(client, {"readme.md": "---\n- a\n- b\n---\n\nx"})
    assert r.status_code == 422 and "frontmatter" in r.json()["message"]


def test_object_directory_rules(client, home, svc):
    from memorytalk.backend.services.collections import CollectionsError
    assert client.post(f"/api/collections/card/{IP}.issue/里面的卡", json={"files": {"readme.md": ""}}).status_code == 422   # 嵌套
    client.post(f"/api/collections/issue/{IP}", json={"files": {"readme.md": ""}})
    r = client.post("/api/collections/origin/" + IP + ".issue/attach.txt", json={"content": "x"})
    assert r.status_code == 400 and "对象目录里" in r.json()["message"]                                     # origin 不能进对象目录
    spec = svc.collections.layer("issue")
    assert spec.check_object_path("a/b", inside_object=False) is None
    assert "不能放在别的对象目录里" in spec.check_object_path("a/b", inside_object=True)


def test_one_bad_file_rejects_the_whole_batch(client, svc, issue):
    r = _put(client, {"positions/乙.md": "b", "extra.txt": "x"})
    assert r.status_code == 422
    assert svc.collections.repo.read(f"{IP}.issue/positions/乙.md") is None


def test_who_and_when_live_in_git(client, H, issue):
    _put(client, {"positions/乙.md": "b"}, headers=H("alice"), subject=f"position {IP}: 乙")
    _put(client, {A: "为什么\n\n## 论证\n- 够用\n"}, headers=H("bob"), subject=f"argue {IP}#只用环境变量: 够用")
    assert git_authors(client, 2)[0::2] == ["bob", "alice"]
