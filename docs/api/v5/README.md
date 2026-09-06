# API Reference (v5)

本地 API,全部挂在 `/api/` 下,请求 / 响应 JSON。**task / server / issue / card 四层都有最简实现。** 起服务 `cd backend && python -m backend serve`,`http://127.0.0.1:8000/docs` 有 OpenAPI。

- 机制 / 设计决策见 [`../../works/v5/`](../../works/v5/README.md)
- 数据结构 / schema 见 [`../../structure/v5/`](../../structure/v5/README.md)

```
System   GET    /api/system/health                                健康检查
         GET    /api/system/info                                  路径 / tmux socket / 有没有窗

Tasks    GET    /api/tasks                                        task 树(森林;root= 只看一棵)
         POST   /api/tasks                                        开工:建 task(parent= 挂到树上)
         GET    /api/tasks/{id}                                   读
         PATCH  /api/tasks/{id}                                   改目标 / 项目 / 状态
         GET    /api/tasks/{id}/events                            task 时间线
         GET    /api/tasks/{id}/recall                            开工注入:card 目录文本
         GET    /api/tasks/{id}/canvas                            画布
         PUT    /api/tasks/{id}/canvas                            全量写画布(version 乐观锁)
         GET    /api/tasks/{id}/sessions                           会话清单
         POST   /api/tasks/{id}/sessions                           打开一个块:协议 → server 建现场
         POST   /api/tasks/{id}/sessions/{sid}/attach              重入
         DELETE /api/tasks/{id}/sessions/{sid}                     关闭即回收
         GET    /api/tasks/{id}/sessions/{sid}/capture             抓终端屏幕
         GET    /api/tasks/{id}/sessions/{sid}/rounds              agent 会话痕迹

Servers  GET    /api/servers                                      server 清单及各自响应的协议
         GET    /api/servers/resolve?uri=                         一个 URI 会请求到谁

Cards    GET    /api/cards                                        目录
         GET    /api/cards/recall                                 目录文本
         GET    /api/cards/search?q=                              git grep
         POST   /api/cards                                        写卡
         GET    /api/cards/{id}                                   读(rev= 读历史版本)
         PUT    /api/cards/{id}                                   改
         DELETE /api/cards/{id}                                   废弃
         GET    /api/cards/{id}/history                           git log
         POST   /api/cards/{id}/issue                             对卡开讨论页

Issues   GET    /api/issues                                       清单(manager_task= / unmanaged=)
         GET    /api/issues/search?q=                             git grep
         POST   /api/issues                                       提问题
         GET    /api/issues/{id}                                  读(立场按 credence 排)
         GET    /api/issues/{id}/history                          git log
         POST   /api/issues/{id}/positions                        加立场
         POST   /api/issues/{id}/positions/{pid}/arguments        表态
         POST   /api/issues/{id}/positions/{pid}/tasks            派出论证 task
         PUT    /api/issues/{id}/manager                          绑 / 换 / 解绑 manager
         POST   /api/issues/{id}/links                            IBIS 边
         POST   /api/issues/{id}/card                             争出结果写成卡
```

分页面:[system.md](system.md) · [tasks.md](tasks.md) · [servers.md](servers.md) · [cards.md](cards.md) · [issues.md](issues.md)

## 通用约定

- **错误体**:`{"error": "<机器码>", "message": "<人读>"}`。

  | 状态 | `error` | 何时 |
  |---|---|---|
  | 400 | `bad_uri` / `no_server` / `cmd_not_found` | URI 没协议 / 连 default 都没有 / 要跑的命令不在 PATH |
  | 404 | `not_found` | task / session / card / issue / position 不存在 |
  | 409 | `exists` | 建卡时 id 已存在 |
  | 409 | `conflict` | task 状态规则、画布 version / 越界、已结束的 task 不能 attach、把手没有该能力 |
  | 422 | (FastAPI 默认) | 请求体校验失败 |
  | 500 | `git` | git 命令失败 |
  | 502 | `platform` | tmux 起不来 |

- **写动作即 commit**(card / issue):写请求可带 `reason`(进 commit message 的 `Reason:`)和 `origin` `{"task_id", "rounds": [int]}`(进 `Task:` / `Rounds:`)。两个跨对象的决定——`POST /api/issues/{id}/card`、`POST /api/cards/{id}/issue`——issue 和 card 落在**同一个 commit**。
- **时间**:ISO 8601 UTC `2026-09-05T23:02:07Z`。
- **HTTP 方法**:读 GET;建 POST;全量替换 PUT;部分改 PATCH;删 / 废弃 DELETE。
- **无分页**:量级小,列表全量返回;`history` 最多 50 条。
- **没有鉴权、没有网关**:ttyd / 反代 / 静态托管随前端一起做。

## ID

| 对象 | 形态 |
|---|---|
| task | `task_<时间戳><4hex>` |
| session | `<task_id>-s<n>`(同时是 tmux 会话名) |
| issue | `iss_<时间戳><4hex>`;position `p<n>`;argument `a<n>` |
| card | 仓库内相对路径 `<dir>/<slug>`,不含 `.md`;路径里可含 `/` 和中文,直接放在 URL 里 |

## 磁盘

```
~/.memory.talk/memory/   git 仓库:cards/<dir>/<slug>.md + issues/<id>.json
~/.memory.talk/tasks/    裸文件:<task_id>/{task,canvas,sessions}.json + events.jsonl + sessions/<session>/rounds.jsonl
```

环境变量 `MEMORY_TALK_HOME` / `MEMORY_TALK_AUTHOR` / `MEMORY_TALK_EMAIL` / `MEMORY_TALK_WORKSPACE` / `MEMORY_TALK_TMUX_SOCKET` / `MEMORY_TALK_TTYD_URL` / `MEMORY_TALK_CLAUDE_PROJECTS` / `MEMORY_TALK_CODEX_SESSIONS` / `MEMORY_TALK_KIMI_SESSIONS`,含义见 [`../../structure/v5/filesystem.md`](../../structure/v5/filesystem.md)。
