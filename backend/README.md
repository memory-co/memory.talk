# backend(v5)

memory.talk v5 的后端骨架。**目前全部是空文件,只立结构,不做实现。** 每个包对应 [docs/works/v5](../docs/works/v5/README.md) 的一篇设计;底层逻辑照 shellbase `server/shellbase/` 原生实现。

```
backend/
├── pyproject.toml            # 独立分发(hatchling);前端产物随包
├── memorytalk/
│   ├── main.py               # FastAPI 实例、路由挂载、启动钩子
│   ├── cli.py                # start / stop / status / daemon / serve(照 shellbase cli)
│   ├── config.py             # 环境变量与路径(~/.memory.talk/{memory,tasks})
│   ├── gateway.py            # AuthGate + 静态托管 + 反代(/tty、/proxy/<port>)
│   ├── auth.py               # token → Cookie
│   ├── system.py             # /api/system/{info,health}
│   │
│   ├── task/                 # 做事层 —— docs/works/v5/task.md
│   │   ├── tree.py           #   task 树:节点、父子、状态、完成收拢
│   │   ├── canvas.py         #   画布(24×16 网格剖分)—— task 的视图,可随时重排
│   │   ├── members.py        #   成员登记:成员 id ↔ URI ↔ server ↔ 活着(唯一权威,脱离布局)
│   │   ├── sessions.py       #   agent 成员的 rounds.jsonl(append-only)
│   │   ├── events.py         #   task 自己的 append-only 事件(开工/状态/做完)
│   │   └── api.py            #   /api/tasks/…
│   │
│   ├── server/               # 协议 server —— docs/works/v5/protocol-server.md
│   │   ├── base.py           #   Server 契约:claims(scheme) / open(id, uri) → 窗 + 把手 / destroy
│   │   ├── registry.py       #   协议 → server 的解析(名单优先于约定,找不到明确报错)
│   │   ├── terminal.py       #   bash:// + 任何 PATH 命令名(tmux 现场)
│   │   ├── agent.py          #   claude:// codex://:终端把手 + 读会话 round
│   │   ├── browser.py        #   https:// http://(本地服务经代理、外链直嵌;把手为空)
│   │   ├── files.py          #   file://
│   │   ├── adapters/         #   读各平台会话记录(来自 v3 adapters,归入 agent server 把手)
│   │   │   ├── base.py / claude_code.py / codex.py
│   │   └── api.py            #   /api/servers/attach?uri=…、DELETE
│   │
│   ├── issue/                # 议事层 —— docs/works/v5/issue.md
│   │   ├── model.py          #   Issue / Position / Argument
│   │   ├── repo.py           #   读写 memory 仓库里的 issues/(每个动作一个 commit)
│   │   ├── links.py          #   IBIS 边(specializes / suggested_by / questions / replaces / related)
│   │   ├── manager.py        #   manager 绑定、派出论证 task、胜出立场 → task 节点
│   │   ├── annotation.py     #   逐 round 标注、#问题 → 在 issue 目录里指认 / 新建
│   │   └── api.py            #   /api/issues/…
│   │
│   ├── card/                 # 记事层 —— docs/works/v5/card.md
│   │   ├── model.py          #   Card:标题、正文、语境、链接
│   │   ├── repo.py           #   读写 memory 仓库里的 cards/(改卡 = commit,历史 = git log)
│   │   ├── catalog.py        #   目录:按目录分层的标题清单
│   │   ├── recall.py         #   task 开工时注入目录
│   │   └── api.py            #   /api/cards/…
│   │
│   └── store/                # 存储 —— docs/works/v5/store.md
│       ├── paths.py          #   ~/.memory.talk 布局
│       ├── files.py          #   裸文件原语:原子写、单写者、无缓存直读(task 用)
│       ├── git.py            #   git 仓库封装:一个决定一个 commit、log、revert
│       └── memory.py         #   memory/ 仓库布局:cards/ + issues/
│
└── tests/                    # 按场景组织,每个目录一个场景(照 shellbase tests/)
```
