"""collections/user_layer -- a .py under <home>/layers is a layer. See README.md."""
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests._util import git_log

EXPERIMENT = '''
import fnmatch
from memorytalk.backend.services.collections.layers import Layer, appended_only, load_yaml

class Experiment(Layer):
    name = "experiment"
    files = ["readme.md", "result.yaml", "runs/*.md"]
    description = "一次实验"

    def check(self, changes, after):
        for c in changes:
            if c.path == "readme.md":
                if c.new is None:
                    return "readme.md 不能删"
            elif c.path == "result.yaml":
                if c.new is not None and "verdict" not in load_yaml(c.new):
                    return "result.yaml 要有 verdict"
            elif fnmatch.fnmatchcase(c.path, "runs/*.md"):
                if c.old is not None and c.new is not None and not appended_only(c.old, c.new):
                    return f"{c.path}:只能在末尾追加"
            else:
                return f"{c.path}:experiment 目录里只能有 readme.md / result.yaml / runs/*.md"
        return None if "readme.md" in after else "缺 readme.md"
'''
OK = {"readme.md": "测什么", "result.yaml": "verdict: 支持", "runs/1.md": "第一次"}


def _app():
    from memorytalk.backend.config import load_config, load_runtime_config
    from memorytalk.backend.main import create_app
    return create_app(load_config(), load_runtime_config())


@pytest.fixture
def client(home):
    d = Path(os.environ["MEMORY_TALK_HOME"]) / "layers"
    d.mkdir(parents=True)
    (d / "experiment.py").write_text(EXPERIMENT)
    with TestClient(_app()) as c:
        yield c


def test_layer_is_loaded_above_the_builtins(client):
    ls = client.get("/api/collections/layers").json()
    assert [(l["name"], l["builtin"]) for l in ls] == [("origin", True), ("issue", True), ("card", True), ("experiment", False)]
    assert ls[-1]["files"] == ["readme.md", "result.yaml", "runs/*.md"]
    cfg = client.get("/api/collections/config").json()["config"]
    assert cfg["layers"][-1] == {"name": "experiment", "builtin": False}


def test_objects_go_through_its_check(client):
    r = client.post("/api/collections/experiment/基准/跑一次", json={"files": OK})
    assert r.status_code == 201 and r.json()["title"] == "跑一次"
    assert "[experiment] write" in git_log(client, "layer/experiment")
    bad = lambda files: client.post("/api/collections/experiment/基准/坏", json={"files": files}).json()["message"]
    assert "缺 readme.md" in bad({"result.yaml": "verdict: x"})
    assert "verdict" in bad({"readme.md": "", "result.yaml": "note: x"})
    assert "extra.txt" in bad({"readme.md": "", "extra.txt": "x"})
    put = lambda files: client.put("/api/collections/experiment/基准/跑一次", json={"files": files})
    assert put({"runs/1.md": "第一次\n第二次"}).status_code == 200
    assert "追加" in put({"runs/1.md": "重写"}).json()["message"]


def test_file_without_a_layer_class_fails_startup(home):
    d = Path(os.environ["MEMORY_TALK_HOME"]) / "layers"
    d.mkdir(parents=True)
    (d / "empty.py").write_text("x = 1\n")
    with pytest.raises(ValueError, match="Layer 的子类"):
        _app()


def test_removing_the_file_after_use_fails_startup(client):
    client.post("/api/collections/experiment/基准/跑一次", json={"files": OK})
    (Path(os.environ["MEMORY_TALK_HOME"]) / "layers" / "experiment.py").unlink()
    from memorytalk.backend.services.collections import CollectionsError
    with pytest.raises(CollectionsError, match="experiment"):
        _app()
