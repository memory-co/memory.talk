# explore — memory.talk explore 命令面

`cli/explore.py`。

## 这个场景在测什么

`memory.talk explore {create, view, list}` 的命令注册、`--help` 形状、参数 →
HTTP 请求接线(`api()` monkeypatch,只验调用对不对)。

## 不在这测什么

- HTTP 行为本身 → `tests/api/explores/`
