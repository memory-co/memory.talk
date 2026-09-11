# tests

**场景化**:每个目录一个场景,自带 `README.md`(在测什么 / 不在这测什么 / fixture 来源)和 `test.py`;test.py 里每个函数只断言一件事,函数名就是结论。目录按层分:`providers/` `collections/` `works/` `work_servers/` `adapters/` `users/` `cli/`。

```
pip install -e ".[dev]" && pytest          # 全部
pytest tests/collections/layer_guard        # 单个场景
```

## 公共 fixture(`conftest.py`)

| fixture | 给什么 |
|---|---|
| `home` | 临时 `MEMORY_TALK_HOME` / workspace / 各平台会话记录根 / 独立 tmux socket;**按 `fs` 和 `sqlite` 两种 store 各跑一遍**(参数化) |
| `client` | 直连 ASGI 的 `TestClient`;已注册 `alice` / `bob` / `carol`;`.json()` 解掉响应信封(成功给 `data`,出错给整个信封) |
| `svc` | `client.app.state`:`collections` / `works` / `users` / `work_servers` / `store`,给要直接碰服务层的场景 |
| `H(user)` | 返回带 `X-Memory-Talk-User` 的 headers 的小函数 |

需要 tmux 的场景标了 `needs_tmux`,机器上没有就跳过。
