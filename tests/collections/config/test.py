"""collections/config -- collections.json anchor. See README.md."""
import json
import pytest
import subprocess

DECISION = """
from memorytalk.backend.services.collections.layers import Layer

class Decision(Layer):
    name = "decision"
    files = ["readme.md"]
    def check(self, changes, after):
        return None if "readme.md" in after else "缺 readme.md"
"""


def _restart_with_layer(name, source):
    """往 <home>/layers 放一个 .py,再起一个 app(层在启动时载入)。"""
    import os
    from pathlib import Path
    from fastapi.testclient import TestClient
    from memorytalk.backend.config import load_config, load_runtime_config
    from memorytalk.backend.main import create_app
    d = Path(os.environ["MEMORY_TALK_HOME"]) / "layers"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.py").write_text(source)
    return TestClient(create_app(load_config(), load_runtime_config()))


def test_anchor_is_the_only_file_in_the_root_commit(svc):
    root = svc.collections.repo.root
    first = subprocess.run(["git", "rev-list", "--max-parents=0", "stack"], cwd=root, capture_output=True, text=True).stdout.split()[0]
    files = subprocess.run(["git", "ls-tree", "-r", "--name-only", first], cwd=root, capture_output=True, text=True).stdout.split()
    assert files == ["collections.json"]


def test_config_lists_builtin_layers_bottom_first(client):
    cfg = client.get("/api/collections/config").json()["config"]
    assert cfg["version"] == 1
    assert [(l["name"], l.get("builtin")) for l in cfg["layers"]] == [("origin", True), ("issue", True), ("card", True)]


def test_a_new_layer_file_is_registered_by_a_commit_on_startup(client):
    with _restart_with_layer("decision", DECISION) as c2:
        r = c2.get("/api/collections/config").json()
    assert r["config"]["layers"][-1] == {"name": "decision", "builtin": False}
    assert r["history"][0]["subject"] == "[origin] collections: add layers decision"
    assert r["history"][-1]["subject"].startswith("[origin] collections: init")


def test_no_other_mechanism_files_in_the_repo(client, svc):
    with _restart_with_layer("decision", DECISION):
        pass
    files = set(svc.collections.repo.tree())
    assert files == {"collections.json"}


@pytest.mark.skip(reason="/api/collections/manager 暂时注释掉了,等 work 实现后一起启用")
def test_config_file_is_invisible_to_tree_catalog_and_inbox(client):
    assert client.get("/api/collections/tree").json() == []
    assert client.get("/api/collections/origin").json()["objects"] == []
    w = client.post("/api/works", json={"goal": "x"}).json()
    client.put("/api/collections/manager", params={"path": ""}, json={"work": w["id"]})
    with _restart_with_layer("decision", DECISION):
        pass
    assert client.get(f"/api/works/{w['id']}/inbox").json() == []
