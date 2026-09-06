# Server + Window + Handle + Live

把块变成现场的那一层。**运行时对象,不落盘**——落盘的是 task 的成员登记([task.md](task.md#member))。机制见 [`../../works/v5/protocol-server.md`](../../works/v5/protocol-server.md)。

## ParsedUri

`scheme:///path?query` 解析结果:

| 字段 | 说明 |
|---|---|
| `raw` | 原样 |
| `scheme` | 小写协议名;终端类 = 命令名 |
| `path` | 终端类:工作目录(是文件则 cwd = 父目录、文件名作参数);`/` 或空 = 默认工作区 |
| `host` / `port` | http 类:`localhost` / `127.0.0.1` + 端口 → 本地服务 |
| `query` | 参数字典(v5 没有身份参数——身份在成员 id 上) |

## ServerInfo

`GET /api/servers` 每项:

```json
{"name": "bash", "claims": ["bash", "*"], "description": "bash:// 以及任何 PATH 里的命令名 → tmux 会话(约定优于注册)"}
```

`claims` 里的 `"*"` 表示按约定兜底(PATH 里有的命令名都认)。解析顺序:显式名单 → 兜底;名单里先排的先赢。

| server | 认领 | 现场 | 窗 | 把手 |
|---|---|---|---|---|
| `claude` / `codex` / `kimi` | 各自协议名 | tmux 会话跑该 CLI | ttyd | `capture` `send` `rounds` |
| `bash` | `bash` + 任何 PATH 命令名 | tmux 会话 | ttyd | `capture` `send` |
| `http` | `http` `https` | 无(纯 iframe) | URL 本身 | 无 |

## Window

```json
{"url": "http://127.0.0.1:7681/?arg=task_…-m1", "embed": "http://127.0.0.1:7681/?arg=task_…-m1"}
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
  "member_id": "task_…-m1", "server": "codex",
  "window": {"url": null, "embed": null},
  "handle": {"kind": "tmux+transcript", "capabilities": ["capture", "send", "rounds"]},
  "cwd": "/home/me/memory.talk", "command": ["codex"]
}
```

`POST /api/tasks/{id}/members` 把它并进 `MemberView` 返回(`window` / `handle` 两个字段)。

## ServerError

| `code` | HTTP | 意思 | 下一步 |
|---|---|---|---|
| `bad_uri` | 400 | 没有协议 | 改 URI |
| `no_server` | 400 | 没有 server 认领这个协议,PATH 里也没这个命令 | 换协议 / 装命令 |
| `cmd_not_found` | 400 | server 认领了但命令不在 PATH | 装命令 |
| `platform` | 502 | tmux 起不来 | 查 tmux,别重试 |
