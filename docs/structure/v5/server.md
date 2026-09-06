# Server + Window + Handle + Live

把块变成现场的那一层。**运行时对象,不落盘**——落盘的是 task 的会话登记([task.md](task.md#session))。机制见 [`../../works/v5/protocol-server.md`](../../works/v5/protocol-server.md)。

## ParsedUri

`scheme:///path?query` 解析结果:

| 字段 | 说明 |
|---|---|
| `raw` | 原样 |
| `scheme` | 小写协议名;拿它去 server 那里寻址;default server 把它当命令名 |
| `path` | 终端类:工作目录(是文件则 cwd = 父目录、文件名作参数);`/` 或空 = 默认工作区 |
| `host` / `port` | http 类:`localhost` / `127.0.0.1` + 端口 → 本地服务 |
| `query` | 参数字典(v5 没有身份参数——身份在会话 id 上) |

## ServerInfo

`GET /api/servers` 每项:

```json
{"name": "http", "protocols": ["http", "https"], "description": "网页块:外链直嵌,本地服务经网关代理;把手为空"}
```

| 字段 | 说明 |
|---|---|
| `name` | server 名;`backend/servers/<name>.py` |
| `protocols[]` | 它响应哪些协议,**server 自己声明**;一个 server 可以多个。`default` 的为空——它不声明,专收没人声明的 |

寻址:协议在某个 server 的 `protocols` 里 → 那个;否则 → `default`。列表里 `default` 永远排最后。

| server | 响应 | 现场 | 窗 | 把手 |
|---|---|---|---|---|
| `claude` / `codex` / `kimi` | 各自同名 | tmux 会话跑该 CLI | ttyd | `capture` `send` `rounds` |
| `bash` | `bash` | tmux 会话 | ttyd | `capture` `send` |
| `http` | `http` `https` | 无(纯 iframe) | URL 本身 | 无 |
| `default` | 没人声明的 | tmux 会话里跑「协议名」命令(`vim://` → `vim`) | ttyd | `capture` `send` |

## Window

```json
{"url": "http://127.0.0.1:7681/?arg=task_…-s1", "embed": "http://127.0.0.1:7681/?arg=task_…-s1"}
```

| 字段 | 说明 |
|---|---|
| `url` | 人能直接打开的地址;**`null` = 这个现场没有画面**(没配 ttyd 时终端类就是 `null`,不给一个连不上的地址) |
| `embed` | 画布 iframe 该装的地址;通常同 `url`,本地服务时是 `/proxy/<port>/…` |

## HandleInfo

```json
{"kind": "tmux+transcript", "capabilities": ["capture", "send", "rounds"]}
```

| `kind` | 谁 | `capabilities` |
|---|---|---|
| `tmux` | bash | `capture`(抓屏)`send`(发键,只在进程内) |
| `tmux+transcript` | claude / codex / kimi | 上面两项 + `rounds`(读会话记录) |
| `none` | http | 空 |

把手本体是 Python 对象;API 只报 `HandleInfo`。`send` 不暴露 API。

## Live

一次 open 的结果:

```json
{
  "session_id": "task_…-s1", "server": "codex",   // server 只在内部流转,API 视图不带
  "window": {"url": null, "embed": null},
  "handle": {"kind": "tmux+transcript", "capabilities": ["capture", "send", "rounds"]},
  "cwd": "/home/me/memory.talk", "command": ["codex"]
}
```

`POST /api/tasks/{id}/sessions` 把它并进 `SessionView` 返回(`window` / `handle` 两个字段)。

## ServerError

| `code` | HTTP | 意思 | 下一步 |
|---|---|---|---|
| `bad_uri` | 400 | 没有协议 | 改 URI |
| `no_server` | 400 | 连 default 都没有(只在 `default.py` 被删时出现) | 加回 default |
| `cmd_not_found` | 400 | 要跑的命令不在 PATH(bash / agent 类:server 名;default:协议名) | 装命令 |
| `platform` | 502 | tmux 起不来 | 查 tmux,别重试 |
