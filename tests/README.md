# tests

**场景化**:每个目录一个场景,自带 `README.md`(在测什么 / 不在这测什么 / fixture 来源)和 `test.py`;test.py 里每个函数只断言一件事,函数名就是结论。目录按层分:`providers/` `auth/`(门:setup / 登录 / token) `metas/`(从 `basic/` 看起:两层各一个文件,stack 看到两个) `works/` `work_servers/` `adapters/` `users/` `search/` `cli/`。

```
pip install -e ".[dev]" && pytest          # 全部
pytest tests/metas/layer_guard        # 单个场景
```

## 公共 fixture(`conftest.py`)

| fixture | 给什么 |
|---|---|
| `home` | 临时 `MEMORY_TALK_HOME` / workspace / 各平台会话记录根 / 独立 tmux socket;**按 `fs` 和 `sqlite` 两种 store 各跑一遍**(参数化) |
| `client` | 直连 ASGI 的 `TestClient`;已 setup 出 `admin`(**默认请求头就是 admin 的 token**),并建好 `alice` / `bob` / `carol`;`client.tokens` 是各人的 token;`.json()` 解掉响应信封(成功给 `data`,出错给整个信封) |
| `svc` | `client.app.state`:`metas` / `works` / `users` / `work_servers` / `store`,给要直接碰服务层的场景 |
| `H(user)` | 以某个人的身份请求:返回带他 `Authorization: Bearer` 的 headers;没登录过的注册用户会自动设密码登录一次,不存在的名字给一个无效 token(401) |

需要 tmux 的场景标了 `needs_tmux`,机器上没有就跳过。
