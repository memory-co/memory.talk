# cli —— 命令行

`memory.talk …` 是本地 API 的客户端,**不含业务逻辑**:每个子命令对应一两个端点,解开 `{data, message}` 信封打印;`--json` 打 `data`。命令清单在 [`docs/cli/v5`](../../docs/cli/v5/README.md)。

| 文件 | 命令 | 重点 |
|---|---|---|
| `__init__.py` | — | `build_parser()`:全局 flag(`--server` / `--user` / `--token` / `--work` / `--json`)+ 各组 `register(top)`;`main(argv)`:server 组是本地动作直接跑,其余建 `Api` 后调 `a.fn(api, a)` |
| `_common.py` | — | `Api(server, user, work, token)`:httpx 客户端,token 来自 `--token` / `MEMORY_TALK_TOKEN`,否则 `credentials.json` 里存的(`--user` 挑谁的);`call()` 统一解信封、4xx → `Fail`(401 / 409 setup_required 时提示先 login / setup)。`out()` 输出、`value()`(`@file` / `@-`)、`parse_fields()`(`--field k=v`)、`Fail`(带 exit code 的异常) |
| `server.py` | `server start / stop / restart / status / daemon` | 后台守护:`instance.json` 记 pid / url,`_alive` / `_health` 判活;`daemon` 就是 uvicorn |
| `auth.py` | `setup / login [name] / logout` | token 存 `<home>/credentials.json`,按服务地址分开、一个地址可存几个人(`saved_token` / `_remember`);密码从 `--password` / `MEMORY_TALK_PASSWORD` / getpass 来 |
| `user.py` | `user add / list / show / set / whoami / passwd` | `add` 只有 admin 能用;`passwd` 自己的要旧密码,admin 给别人设不用 |
| `work.py` | `work create / list / show / set / attach / sessions / detach / capture / rounds / inbox / manager / users / touch / servers` | `w_list` 递归打树 |
| `collection.py` | `collection(col) layers / tree / recent / read / write / edit / rm / log / manager / managed` | `_body()` 把 `--put 文件=内容`(或 origin 的 `--content`)+ `--subject` / `--reason` 拼成请求体 |
| `search.py` | `search <q>` | 按 kind 分组打印 |
