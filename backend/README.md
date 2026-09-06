# backend(v5)

memory.talk v5 的后端。**task / server / issue / card 四层都有最简实现(git + 裸文件存储,FastAPI,真 tmux)。** 未做:鉴权网关、ttyd / 反代托管、`daemon` / `start` / `stop`、逐 round 标注(`annotation.py` 仍为空)。 端点清单见 [docs/api/v5](../docs/api/v5/README.md);起服务 `python -m backend serve`,测试 `pytest`。 按 **models / services / controllers** 三层分目录,外加 **servers/**(每个协议一个 server);services 下每个子包对应 [docs/works/v5](../docs/works/v5/README.md) 的一篇设计;底层逻辑照 shellbase `server/shellbase/` 原生实现。`backend/` 本身就是 Python 包根,不再套一层包名目录。

```
backend/
├── pyproject.toml            # 独立分发(hatchling);前端产物随包
├── main.py                   # FastAPI 实例、路由挂载、启动钩子
├── cli.py                    # start / stop / status / daemon / serve(照 shellbase cli)
├── config.py                 # 环境变量与路径(~/.memory.talk/{memory,tasks})
├── gateway.py                # AuthGate + 静态托管 + 反代(/tty、/proxy/<port>)
│
├── models/                   # 数据模型(纯结构,不含 IO)
│   ├── task.py               #   Task 节点(目标、状态、父子)、Canvas、Session、Round、Event
│   ├── issue.py              #   Issue / Position / Argument / Link(IBIS 边)
│   ├── card.py               #   Card:标题、正文、语境、链接
│   └── server.py             #   Server 契约:name + protocols(声明响应哪些协议)/ open(id, uri) → Window + Handle / handle / alive / destroy
│
├── services/                 # 业务逻辑(每个子包对应一篇设计;**入口就是子包的 `__init__.py`**,导出该 service 类,main.py 按 `services/*` 扫描装配,不另加约定)
│   ├── task/                 #   做事层 —— docs/works/v5/task.md
│   │   ├── __init__.py       #     入口:导出 TaskService(对外唯一门面)
│   │   ├── tree.py           #     task 树:建节点、父子、状态、完成收拢
│   │   ├── canvas.py         #     画布(24×16 网格剖分)—— task 的视图,可随时重排
│   │   ├── sessions.py       #     会话(现场)登记:会话 id ↔ URI ↔ server ↔ 活着(唯一权威,脱离布局)
│   │   ├── members.py        #     成员(人):谁在操作 / 操作过,只做可见性不做权限(身份来自 X-Memory-Talk-User)
│   │   ├── rounds.py         #     agent 会话的 rounds.jsonl(append-only)
│   │   └── events.py         #     task 自己的 append-only 事件(开工/状态/做完)
│   ├── servers/              #   server 的装载与分发 —— docs/works/v5/protocol-server.md
│   │   ├── registry.py       #     协议 → server 寻址:先看谁声明了它,没人声明去 default
│   │   ├── uri.py            #     块的 URI 解析
│   │   ├── terminal.py       #     tmux 现场 + 终端类 server 基类(TerminalBase)
│   │   ├── agent.py          #     agent 类 server 基类(AgentBase:终端把手 + 读 round)
│   │   └── adapters/         #     读各平台会话记录:claude_code / codex / kimi
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
├── servers/                  # 每个 server 一个文件,自己声明响应哪些协议(自动扫描);没人声明的协议去 default
│   ├── bash.py               #   bash
│   ├── claude.py             #   claude     Claude Code
│   ├── codex.py              #   codex      Codex
│   ├── kimi.py               #   kimi       Kimi Code
│   ├── http.py               #   http + https  浏览器块(把手为空)
│   └── default.py            #   兜底:协议名当命令名在 tmux 里跑(vim:// htop:// …),背后是 bash 但调用方不感知
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
