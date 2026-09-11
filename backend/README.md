# backend(v5)

memory.talk v5 的后端。**work 树(带 created_by 与 users)、协议 server、Collections(origin / issue / card 三层 + 用户层,提交 author = user)、manager 收件箱、存储 provider(LocalFS / SQLite,测试两种都跑)都有最简实现。** 未做:鉴权网关、ttyd / 反代托管、`daemon` / `start` / `stop`、逐 round 标注、二进制 blob 外置、给人手工 `git commit` 用的 hook(服务进程是唯一写者)。 端点清单见 [docs/api/v5](../docs/api/v5/README.md);起服务 `python -m backend serve`,测试 `pytest`。 按 **models / services / controllers** 三层分目录,外加 **servers/**(每个协议一个 server)和 **layers/**(每个内置 layer 一个文件);services 下每个子包对应 [docs/designs/v5](../docs/designs/v5/README.md) 的一篇设计;底层逻辑照 shellbase `server/shellbase/` 原生实现。`backend/` 本身就是 Python 包根,不再套一层包名目录。

```
backend/
├── pyproject.toml            # 独立分发(hatchling);前端产物随包
├── main.py                   # FastAPI 实例、路由挂载、启动钩子
├── cli.py                    # start / stop / status / daemon / serve(照 shellbase cli)
├── config.py                 # 环境变量与路径(~/.memory.talk/{memory,works})
├── gateway.py                # AuthGate + 静态托管 + 反代(/tty、/proxy/<port>)
│
├── models/                   # 数据模型(纯结构,不含 IO)
│   ├── users.py              #   User / UserProfile(汇总视图,不落盘)
│   ├── work.py               #   Work 节点(目标、created_by、状态、父子)、Canvas、Session、WorkUser、Round、Event
│   ├── collections.py            #   LayerInfo / Obj / Revision / SearchHit / Catalog / Tree / Manager / InboxItem
│   └── server.py             #   Server 契约:name + protocols(声明响应哪些协议)/ open(id, uri) → Window + Handle / handle / alive / destroy
│
├── services/                 # 业务逻辑(每个子包对应一篇设计;**入口就是子包的 `__init__.py`**,导出该 service 类,main.py 按 `services/*` 扫描装配,不另加约定)
│   ├── work/                 #   做事层 —— docs/designs/v5/work.md
│   │   ├── __init__.py       #     入口:导出 WorkService(对外唯一门面)
│   │   ├── tree.py           #     work 树:建节点、父子、状态、完成收拢
│   │   ├── canvas.py         #     画布(24×16 网格剖分)—— work 的视图,可随时重排
│   │   ├── sessions.py       #     会话(现场)登记:会话 id ↔ URI ↔ server ↔ 活着(唯一权威,脱离布局)
│   │   ├── users.py          #     user:谁动过这个 work,只做可见性不做权限(身份来自 X-Memory-Talk-User)
│   │   ├── repo.py           #     WorkRepo:业务仓储接口 + fs 版 / db 版两份实现(业务概念在这,provider 只见字节 / 表)
│   │   ├── rounds.py         #     agent 会话的 rounds.jsonl(append-only)
│   │   ├── inbox.py          #     收件箱:manager.json 路由过来的变动(append-only)
│   │   └── events.py         #     work 自己的 append-only 事件(开工/状态/做完)
│   ├── work_servers/         #   work server 的装载与寻址 —— docs/designs/v5/work-server.md
│   │   ├── registry.py       #     协议 → server 寻址:先看谁声明了它,没人声明去 default
│   │   ├── uri.py            #     块的 URI 解析
│   │   ├── terminal.py       #     tmux 现场 + 终端类 server 基类(TerminalBase)
│   │   ├── agent.py          #     agent 类 server 基类(AgentBase:终端把手 + 读 round)
│   │   └── adapters/         #     读各平台会话记录:claude_code / codex / kimi
│   ├── users/                #   UserService:从 work 与 collections 汇总 user(不注册)—— docs/designs/v5/user.md
│   ├── collections/              #   认知层 —— docs/designs/v5/collections.md / manager.md
│   │   ├── repo.py           #     分层 git(自己实现):layer/<名> 权威分支 + stack merge 视图 + 路径归属守卫;纯 plumbing
│   │   ├── manager.py        #     manager.json:最近祖先解析
│   │   ├── catalog.py        #     一层的目录(按目录树列标题)+ 召回文本
│   │   └── __init__.py       #     CollectionsService:层的装载(内置 + schemas/*.yaml)、对象 CRUD、历史、检索、树、行为、manager、投递到收件箱
│   └── store/                #   装配 —— docs/designs/v5/provider.md
│       └── __init__.py       #     StoreService:按 MEMORY_TALK_STORE 选 provider,按族建 work 仓储
│
├── providers/                # 存储介质的两族基类(只有介质原语,没有业务)—— docs/designs/v5/provider.md
│   ├── fs.py                 #   FileSystemProvider(read/write/append/list/…,能力 local_path)+ LocalFS
│   └── db.py                 #   DatabaseProvider(表定义 + 链式 select/insert/update/delete,方言在内)+ SQLite
│
├── layers/                   # 每个内置 layer 一个文件;用户层来自仓库里的 schemas/<name>.yaml
│   ├── _spec.py              #   LayerSpec:名字 + 形态(后缀 / 本体文件 / 格式)+ schema + 行为
│   ├── _user.py              #   YAML 字段表 → LayerSpec(用户层,无行为)
│   ├── origin.py             #   最底层:不带后缀的一切,原文
│   ├── issue.py              #   <名>.issue/issue.json;行为 position / argue / link / spawn / decide
│   └── card.py               #   <名>.card/card.md;行为 discuss
│
├── work_servers/             # 每个 work server 一个文件,自己声明响应哪些协议(自动扫描);没人声明的协议去 default
│   ├── bash.py               #   bash
│   ├── claude.py             #   claude     Claude Code
│   ├── codex.py              #   codex      Codex
│   ├── kimi.py               #   kimi       Kimi Code
│   ├── http.py               #   http + https  浏览器块(把手为空)
│   └── default.py            #   兜底:协议名当命令名在 tmux 里跑(vim:// htop:// …),背后是 bash 但调用方不感知
│
├── controllers/              # HTTP 面(FastAPI 路由;只做参数/响应,不含逻辑)
│   ├── works.py              #   /api/works/…
│   ├── users.py              #   /api/users/…(顶层:list / me / {name})
│   ├── collections.py            #   /api/collections/…(层、树、检索、manager、对象 CRUD、历史、行为)
│   ├── auth.py               #   /api/auth/{login,verify,logout,me}
│   └── system.py             #   /api/system/{info,health}
│
└── tests/                    # 按场景组织,每个目录一个场景(照 shellbase tests/)
```
