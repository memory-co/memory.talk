"""metas/layer_guard -- path ownership by layer. See README.md."""
import pytest

from memorytalk.backend.services.metas import MetasError, Ctx
from tests._util import git_log

IP = "memory.talk/配置/该走文件还是环境变量"


def test_cross_layer_commit_is_rejected(client, svc):
    client.post(f"/api/metas/issue/{IP}", json={"files": {"readme.md": ""}})
    with pytest.raises(MetasError) as e:
        svc.metas.commit("card", "touch", {f"{IP}.issue/readme.md": b"x"}, [], "", Ctx())
    assert e.value.code == "guard" and "[issue]" in str(e.value)


def test_same_layer_edit_passes(client, svc):
    client.post(f"/api/metas/issue/{IP}", json={"files": {"readme.md": ""}})
    assert svc.metas.commit("issue", "edit", {f"{IP}.issue/readme.md": "改了".encode()}, [], "", Ctx())


def test_each_layer_branch_only_has_its_own_commits(client):
    client.post(f"/api/metas/issue/{IP}", json={"files": {"readme.md": ""}})
    client.post("/api/metas/card/x/卡", json={"files": {"readme.md": "卡"}})
    assert "[card]" not in git_log(client, "layer/issue") and "[issue]" not in git_log(client, "layer/card")
    stack = git_log(client, "stack")
    assert "[issue] write" in stack and "[card] write" in stack
