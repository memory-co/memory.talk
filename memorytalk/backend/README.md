# memorytalk/backend(v5 服务)

memory.talk v5 的 Python 包(pip:`memorytalk`,命令 `memory.talk`)。**work 树(带 created_by 与 users)、协议 server、Collections(origin / issue / card 三层 + 用户层;每层是一份 YAML 协议,一个引擎校验;提交 author = user)、manager 收件箱、存储 provider(LocalFS / SQLite,测试两种都跑)都有最简实现。** 门(setup / 登录 / token,`main.py` 的中间件)也有。未做:ttyd / 反代托管、`daemon` / `start` / `stop`、逐 round 标注、二进制 blob 外置、给人手工 `git commit` 用的 hook(服务进程是唯一写者)。 每个目录下有自己的 README 说明用途和重点函数(controllers / models / providers / services 各子包 / work_servers);端点清单见 [docs/api/v5](../docs/api/v5/README.md);起服务 `memory.talk server start`,测试在仓库根 `pytest`。 按 **models / services / controllers** 三层分目录,外加 **work_servers/**(每个协议一个 server);内置 layer 定义在 services/collections/layers/ 下;services 下每个子包对应 [docs/designs/v5](../docs/designs/v5/README.md) 的一篇设计;底层逻辑照 shellbase `server/shellbase/` 原生实现。

```
memorytalk/backend/           # 服务本体;memorytalk/cli/ 是它的命令行客户端
├── main.py                   # FastAPI 实例、路由挂载、启动钩子
├── config.py                 # 环境变量与路径(~/.memory.talk/{collections,layers,works,users})
├── gateway.py                # AuthGate + 静态托管 + 反代(/tty、/proxy/<port>)
│
├── models/                   # 数据模型(纯结构,不含 IO)
│   ├── result.py             #   Result[T]:统一响应信封 {data, message[, error]},每个端点的 response_model
│   ├── users.py              #   User(档案,存;role)/ UserCreate(带初始密码)/ UserView / UserProfile(带派生统计)
│   ├── auth.py               #   AuthStatus / SetupRequest / LoginRequest / LoginResult / PasswordChange
│   ├── work.py               #   Work 节点(目标、created_by、状态、父子)、Canvas、Session、WorkUser、Round、Event
│   ├── collections.py        #   LayerInfo / Obj(目录里的文件)/ ObjWrite / TreeView(items + can_create + candidate)/ CheckResult / Revision / SearchHit / Manager / InboxItem
│   ├── search.py             #   SearchHit(kind: work / collection / user)/ SearchResult
│   └── work_server.py        #   work server 契约:name + protocols / open(id, uri) → Window + Handle / handle / alive / destroy
│
├── services/                 # 业务逻辑(每个子包对应一篇设计;**入口就是子包的 `__init__.py`**,导出该 service 类,main.py 按 `services/*` 扫描装配,不另加约定)
│   ├── README.md             #   整体思路:三条主线(认知层是 git / 现场层介质可换 / 协议自己说)+ 三层怎么接
│   ├── work/                 #   做事层 —— docs/designs/v5/work.md
│   │   ├── __init__.py       #     入口:导出 WorkService(对外唯一门面)
│   │   ├── tree.py           #     work 树:建节点、父子、状态、完成收拢
│   │   ├── canvas.py         #     画布(列 × 会话,可收起)—— work 的视图,可随时重排;会话开 / 关时跟着记
│   │   ├── sessions.py       #     会话(现场)登记:会话 id ↔ URI ↔ server ↔ 活着(唯一权威,脱离布局)
│   │   ├── users.py          #     user:谁动过这个 work,只做可见性不做权限(身份来自登录态)
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
│   ├── users/                #   user:注册的实体 —— docs/designs/v5/user.md
│   │   ├── repo.py           #     UserRepo:fs 版(users/<name>.json)/ db 版(users 表)
│   │   └── __init__.py       #     UserService:注册(密码哈希进记录)/ 档案 / 活动统计(从 work 与 collections 现算)/ commit author
│   ├── auth/                 #   门 —— docs/designs/v5/auth.md
│   │   ├── repo.py           #     TokenRepo:fs 版(auth/tokens/<sha256>.json)/ db 版(auth_tokens 表)
│   │   └── __init__.py       #     AuthService:setup(立 admin)/ 登录换 token / 解析 token / 改密码(作废 token);scrypt 哈希
│   ├── collections/          #   认知层 —— docs/designs/v5/collections.md / manager.md
│   │   ├── layers/           #     层 = 一份 YAML 协议;protocol.py 是唯一引擎(校验 + 给前端的说明);用户层 = <home>/layers/*.yaml(README.md)
│   │   │   ├── protocol.py   #       from_yaml → Layer(object 规则 + 文件种类 + 字段类型);check(diff, after);can_create_files
│   │   │   ├── origin.yaml   #       最底层:不带后缀的一切,原文,不校验
│   │   │   ├── issue.yaml    #       <名>.issue/{readme.md, positions/{name}.md};每个文件 = frontmatter 字段 + 正文
│   │   │   └── card.yaml     #       <名>.card/readme.md;字段 context / links / issue + 正文
│   │   ├── git.py            #     git 原语:hash-object / write-tree / commit-tree / update-ref / ls-tree / show / log / grep,不认识层
│   │   ├── repo.py           #     分层拓扑(在 git.py 上):layer/<名> 权威分支 + stack merge 视图 + 路径归属守卫 + collections.json 锚定
│   │   ├── manager.py        #     manager.json:最近祖先解析
│   │   └── __init__.py       #     CollectionsService:层的装载、对象读(目录里的文件)、写(一批文件改动 → 算 diff → 层的 check → 一个 [层] 提交)、历史、检索、树、manager、投递
│   ├── search/               #   综合搜索:把 q 交给每个 service 的 search(),汇总 —— docs/api/v5/search.md
│   └── store/                #   装配 —— docs/designs/v5/provider.md
│       └── __init__.py       #     StoreService:按 MEMORY_TALK_STORE 选 provider,按族建 work / user 仓储
│
├── providers/                # 存储介质的两族基类(只有介质原语,没有业务)—— docs/designs/v5/provider.md
│   ├── fs.py                 #   FileSystemProvider(read/write/append/list/…,能力 local_path)+ LocalFS
│   └── db.py                 #   DatabaseProvider(表定义 + 链式 select/insert/update/delete,方言在内)+ SQLite
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
│   ├── users.py              #   /api/users/…(list / me / {name} / {name}/password;建账号只有 admin)
│   ├── collections.py        #   /api/collections/…(层、树、最近、对象 CRUD、历史)
│   ├── search.py             #   /api/search(综合搜索)
│   ├── auth.py               #   /api/auth/{status,setup,login,logout} + current_user / require_admin 依赖
│   └── system.py             #   /api/system/{info,health}
│
└── (frontend/ 在 memorytalk/frontend,tests/ 在仓库根)
```
