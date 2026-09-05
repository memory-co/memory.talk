# backend(v5)

memory.talk v5 的后端。**task / server / issue / card 四层都有最简实现(git + 裸文件存储,FastAPI,真 tmux)。** 未做:鉴权网关、ttyd / 反代托管、`daemon` / `start` / `stop`、逐 round 标注(`annotation.py` 仍为空)。 端点清单见 [docs/api/v5](../docs/api/v5/README.md);起服务 `python -m backend serve`,测试 `pytest`。 按 **models / services / controllers** 三层分目录;services 下每个子包对应 [docs/works/v5](../docs/works/v5/README.md) 的一篇设计;底层逻辑照 shellbase `server/shellbase/` 原生实现。`backend/` 本身就是 Python 包根,不再套一层包名目录。

```
backend/
├── pyproject.toml            # 独立分发(hatchling);前端产物随包
├── main.py                   # FastAPI 实例、路由挂载、启动钩子
├── cli.py                    # start / stop / status / daemon / serve(照 shellbase cli)
├── config.py                 # 环境变量与路径(~/.memory.talk/{memory,tasks})
├── gateway.py                # AuthGate + 静态托管 + 反代(/tty、/proxy/<port>)
│
├── models/                   # 数据模型(纯结构,不含 IO)
│   ├── task.py               #   Task 节点(目标、状态、父子)、Canvas、Member、Round、Event
│   ├── issue.py              #   Issue / Position / Argument / Link(IBIS 边)
│   ├── card.py               #   Card:标题、正文、语境、链接
│   └── server.py             #   Server 契约:claims(scheme) / open(id, uri) → Window + Handle / destroy
│
├── services/                 # 业务逻辑(每个子包对应一篇设计;**入口就是子包的 `__init__.py`**,导出该 service 类,main.py 按 `services/*` 扫描装配,不另加约定)
│   ├── task/                 #   做事层 —— docs/works/v5/task.md
│   │   ├── __init__.py       #     入口:导出 TaskService(对外唯一门面)
│   │   ├── tree.py           #     task 树:建节点、父子、状态、完成收拢
│   │   ├── canvas.py         #     画布(24×16 网格剖分)—— task 的视图,可随时重排
│   │   ├── members.py        #     成员登记:成员 id ↔ URI ↔ server ↔ 活着(唯一权威,脱离布局)
│   │   ├── sessions.py       #     agent 成员的 rounds.jsonl(append-only)
│   │   └── events.py         #     task 自己的 append-only 事件(开工/状态/做完)
│   ├── servers/              #   协议 server —— docs/works/v5/protocol-server.md
│   │   ├── __init__.py       #     入口:导出 ServerService(协议 → server 请求;持有 registry)
│   │   ├── registry.py       #     协议 → server 的解析(名单优先于约定,找不到明确报错)
│   │   ├── terminal.py       #     bash:// + 任何 PATH 命令名(tmux 现场)
│   │   ├── agent.py          #     claude:// codex://:终端把手 + 读会话 round
│   │   ├── browser.py        #     https:// http://(本地服务经代理、外链直嵌;把手为空)
│   │   ├── files.py          #     file://
│   │   └── adapters/         #     读各平台会话记录(来自 v3 adapters,归入 agent server 把手)
│   │       └── base.py / claude_code.py / codex.py
│   ├── issue/                #   议事层 —— docs/works/v5/issue.md
│   │   ├── __init__.py       #     入口:导出 IssueService
│   │   ├── repo.py           #     读写 memory 仓库里的 issues/(每个动作一个 commit)
│   │   ├── links.py          #     IBIS 边的建立与查询
│   │   ├── manager.py        #     manager 绑定、派出论证 task、胜出立场 → task 节点
│   │   └── annotation.py     #     逐 round 标注、#问题 → 在 issue 目录里指认 / 新建
│   ├── card/                 #   记事层 —— docs/works/v5/card.md
│   │   ├── __init__.py       #     入口:导出 CardService
│   │   ├── repo.py           #     读写 memory 仓库里的 cards/(改卡 = commit,历史 = git log)
│   │   ├── catalog.py        #     目录:按目录分层的标题清单
│   │   └── recall.py         #     task 开工时注入目录
│   └── store/                #   存储 —— docs/works/v5/store.md
│       ├── __init__.py       #     入口:导出 StoreService(git 仓库 + 裸文件根,其余 service 的依赖)
│       ├── paths.py          #     ~/.memory.talk 布局
│       ├── files.py          #     裸文件原语:原子写、单写者、无缓存直读(task 用)
│       ├── git.py            #     git 仓库封装:一个决定一个 commit、log、revert
│       └── memory.py         #     memory/ 仓库布局:cards/ + issues/
│
├── controllers/              # HTTP 面(FastAPI 路由;只做参数/响应,不含逻辑)
│   ├── tasks.py              #   /api/tasks/…
│   ├── servers.py            #   /api/servers/attach?uri=…、DELETE
│   ├── issues.py             #   /api/issues/…
│   ├── cards.py              #   /api/cards/…
│   ├── auth.py               #   /api/auth/{login,verify,logout,me}
│   └── system.py             #   /api/system/{info,health}
│
└── tests/                    # 按场景组织,每个目录一个场景(照 shellbase tests/)
```
