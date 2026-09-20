# Structure (v5)

v5 的数据模型 —— 描述对象 schema、字段语义、磁盘布局。**是什么**;机制 / 为什么见 [`../../designs/v5/`](../../designs/v5/README.md),HTTP 契约见 [`../../api/v5/`](../../api/v5/README.md)。

v5 的三层:**work**(做事,裸文件)、**issue**(议事,git)、**card**(记事,git),外加把块变成现场的 **server**。没有数据库、没有索引——磁盘上每个字节都是 canonical。

## 对象清单

| 对象 | 形态 | 存哪 | 文档 |
|---|---|---|---|
| Work | 树上一个节点:目标、父、状态(没有 project) | `works/<id>/work.json` | [work.md](work.md) |
| Canvas / Panel | work 的画布:24×16 网格上的块;**视图,可随时重排** | `works/<id>/canvas.json` | [work.md](work.md#canvas) |
| Worklet | work 的工作单元 = 一个现场:URI + 建它的 server;**身份脱离布局** | `works/<id>/worklets.json` | [work.md](work.md#worklet) |
| **User** | 注册的实体,和 work 平级:名字 / 显示名 / 邮箱 / 注册时间 / 角色(admin 只有一个);密码哈希存在记录里不出接口 | `users/<name>.json`(或 `users` 表) | [api users.md](../../api/v5/users.md) |
| Token | 登录态:随机串的 sha256 → 谁的、何时发;logout / 改密码即删 | `auth/tokens/<sha256>.json`(或 `auth_tokens` 表) | [api auth.md](../../api/v5/auth.md) |
| WorkUser | 谁动过这个 work;只做可见性;work 另有 `created_by` 归属(指向一个注册的 User) | `works/<id>/users.json` | [work.md](work.md#workuserusers) |
| Round | agent 工作单元的工作单元痕迹,append-only | `works/<id>/worklets/<worklet>/rounds.jsonl` | [work.md](work.md#round) |
| Event | work 自己的时间线,append-only | `works/<id>/events.jsonl` | [work.md](work.md#event) |
| **Metas**:层 / 对象 / 分层仓库 / manager.json | 认知层。origin / issue / card 三个内置 layer + 用户层;对象 = 带后缀的目录,放哪都行 | `memory/`(分层 git) | [metas.md](metas.md) |
| ↳ issue 层:readme.md / positions/*.md | 问题(目录名;字段 links / summary + 正文)+ 立场(一个一文件;字段 links / rank / verdict + 正文,论证一行一条) | `<path>.issue/` 目录 | [metas.md](metas.md#issue-层内置) |
| ↳ card 层:readme.md | 维基式事实条目:字段 context / links / issue + 正文;标题是目录名;可改可删,历史在 git | `<path>.card/` 目录 | [metas.md](metas.md#card-层内置) |
| ↳ origin 层 | 不带后缀的一切文件,原文 | 任意路径 | [metas.md](metas.md#对象带后缀的目录) |
| Server / Window / Handle / Live | 声明响应哪些协议(没人声明的去 default);建现场、交回窗 + 把手 | 不落盘(运行时对象) | [work-server.md](work-server.md) |

## ID

| 对象 | 形态 | 示例 |
|---|---|---|
| Work | `work_<UTC 时间戳 14 位><4 hex>` | `work_202609052302072f2f` |
| Worklet | `<work_id>-w<n>`,work 内顺序编号;**同时是 tmux 会话名** | `work_2026…2f2f-w1` |
| Issue | `iss_<UTC 时间戳 14 位><4 hex>` | `iss_202609052246183f6a` |
| Position / Argument | issue 内顺序编号 `p<n>` / 立场内顺序编号 `a<n>` | `p2`、`a1`;跨对象引用写 `<issue_id>#p2` |
| Card | **仓库内相对路径**(不含 `.md`),目录即分类 | `memory.talk/配置只来自环境变量` |
| Panel | 前端自定,画布内唯一 | `p1` |

前缀 = 类型。card 没有前缀:它就是一条路径,像维基的词条名。

## 三层怎么互相引用

```
Work ──(worklets)──▶ Worklet ──(server)──▶ 现场(tmux 会话 / 网页)
  ▲                    │
  │ manager.json       └──(rounds.jsonl)──▶ Round  ◀── 论证那一行里的文字可以提到 (work_id#round),系统不解析
  │
Card  ──(issue)──▶ Issue                            ← 卡记讨论页;issue 不记卡(弱耦合)
Issue ──(meta.links)──▶ Issue                       ← IBIS 边
Card  ──(links)──▶ Card                             ← 内链
```

全部是**裸 id 引用,无外键**:work 不知道 issue 的存在(issue 记 `manager_work`,work 侧靠 `GET /api/issues?manager_work=` 反查);card / issue 记的 `work_id` 可以指向已结束甚至已不存在的 work,读时容忍悬挂。

## 磁盘布局速查

```
~/.memory.talk/
├── metas/                    ← git 仓库(认知层 canonical,含全部历史)
│   ├── cards/<dir>/<slug>.md
│   └── issues/<issue_id>.json
└── works/<work_id>/             ← 裸文件(现场 canonical,原子写,不进 git)
    ├── work.json
    ├── canvas.json
    ├── worklets.json
    ├── events.jsonl
    └── worklets/<worklet_id>/rounds.jsonl
```

完整清单见 [filesystem.md](filesystem.md)。

## 不变性一览

| 对象 | 能不能改 | 历史在哪 |
|---|---|---|
| Card | **能改、能删**(像编辑词条);当前实现还有 `deprecated` 状态位,设计上已去掉 | git log |
| Issue 的 question / origin / created_at | 建后不改 | git log |
| Issue 的 manager_work / card / links | 能改(换绑、写卡、连边) | git log |
| Position / Argument | **只增不改不删** | git log(每条一个 commit) |
| Work 的 goal / status | 能改 | events.jsonl(状态变化) |
| Canvas | 能改(全量覆盖,version 乐观锁) | 不留(视图) |
| Worklet | 建 / 删;`last_attached` 会更新 | events.jsonl |
| Round / Event | **只追加** | 自身就是时间线 |

## 现算、不存的量

| 量 | 在哪算 |
|---|---|
| issue 的立场顺序 | 读时按各立场自己的 `rank` 升序,没有 `rank` 的按文件名;不算分 |
| Worklet 的 `alive` | 读工作单元时问 server(`tmux has-session`) |
| Work 树(`children[]`) | 读时从各 `work.json` 的 `parent` 拼出来 |
| Card 目录 | 读时扫 `cards/` 目录树 |
