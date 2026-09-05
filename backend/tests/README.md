# tests

按场景组织:每个目录一个场景,自带 `test.py`。client 走 `httpx.ASGITransport` 直连 ASGI 应用,不起端口;`MEMORY_TALK_HOME` 指到临时目录,每个场景一个干净的 git 仓库。

```
pip install -e ".[dev]" && pytest
```
