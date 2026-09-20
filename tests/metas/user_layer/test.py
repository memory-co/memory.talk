"""metas/user_layer -- a .yaml under <home>/layers is a layer. See README.md."""
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests._util import git_log

EXPERIMENT = """
layer: experiment
description: 一次实验
object: {name: 实验, under: "experiments(/.*)?"}
files:
  - pattern: ^readme\\.md$
    label: 设定
    required: true
    format:
      fields:
        verdict: {type: enum, values: [supports, refutes, inconclusive], required: true}
        ran_at: {type: date}
        issue: {type: ref, layer: issue}
      body: markdown
  - pattern: ^runs/(?P<name>[^/]+)\\.md$
    name: 序号
    label: 一次运行
    format: {body: text}
"""
OK = {"readme.md": "---\nverdict: supports\nran_at: 2026-09-18\n---\n\n测什么", "runs/1.md": "第一次"}


def _app():
    from memorytalk.backend.config import load_config, load_runtime_config
    from memorytalk.backend.main import create_app
    return create_app(load_config(), load_runtime_config())


def _write(name, text):
    d = Path(os.environ["MEMORY_TALK_HOME"]) / "layers"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.yaml").write_text(text)


@pytest.fixture
def client(home):
    _write("experiment", EXPERIMENT)
    with TestClient(_app()) as c:
        c.headers["Authorization"] = "Bearer " + c.post("/api/auth/setup", json={"password": "pw-123456"}).json()["token"]
        yield c


def test_layer_is_loaded_above_the_builtins_with_its_protocol(client):
    ls = client.get("/api/metas/layers").json()
    assert [(l["name"], l["builtin"]) for l in ls] == [("origin", True), ("issue", True), ("card", True), ("experiment", False)]
    assert ls[-1]["protocol"]["object"]["under"] == "experiments(/.*)?" and [f["example"] for f in ls[-1]["protocol"]["files"]] == ["readme.md", "runs/{name}.md"]
    assert client.get("/api/metas/config").json()["config"]["layers"][-1] == {"name": "experiment", "builtin": False}


def test_objects_go_through_the_engine(client):
    r = client.post("/api/metas/experiment/experiments/基准/跑一次", json={"files": OK})
    assert r.status_code == 201 and r.json()["title"] == "跑一次"
    assert "[experiment] write" in git_log(client, "layer/experiment")
    bad = lambda path, files: client.post(f"/api/metas/experiment/{path}", json={"files": files}).json()["message"]
    assert "under" in bad("别处/坏", OK)
    assert "缺 readme.md" in bad("experiments/坏", {"runs/1.md": "x"})
    assert "必填" in bad("experiments/坏", {"readme.md": "---\nran_at: 2026-09-18\n---\n"})
    assert "日期" in bad("experiments/坏", {"readme.md": "---\nverdict: supports\nran_at: 昨天\n---\n"})
    assert "extra.txt" in bad("experiments/坏", {"readme.md": "---\nverdict: supports\n---\n", "extra.txt": "x"})


def test_bad_protocols_fail_startup(home):
    from memorytalk.backend.services.metas import MetasError
    for text, why in [
        ("layer: bad\nfiles:\n  - {pattern: '^a\\.md$', format: {fields: {x: {type: money}}}}\n", "不支持的类型"),
        ("layer: bad\nfiles:\n  - {pattern: '^a\\.md$'}\n  - {pattern: '^(?P<name>[^/]+)\\.md$', name: n}\n", "同一个路径"),
        ("layer: bad\nobject: {pattern: '^(?P<name>.+)$'}\nfiles:\n  - {pattern: '^a\\.md$'}\n", "结尾"),
        ("layer: bad\nfiles:\n  - {pattern: '^a(\\.md$'}\n", "正则"),
        ("layer: other\nfiles:\n  - {pattern: '^a\\.md$'}\n", "不一致"),
    ]:
        _write("bad", text)
        with pytest.raises(MetasError, match=why):
            _app()


def test_removing_the_file_after_use_fails_startup(client):
    client.post("/api/metas/experiment/experiments/基准/跑一次", json={"files": OK})
    (Path(os.environ["MEMORY_TALK_HOME"]) / "layers" / "experiment.yaml").unlink()
    from memorytalk.backend.services.metas import MetasError
    with pytest.raises(MetasError, match="experiment"):
        _app()
