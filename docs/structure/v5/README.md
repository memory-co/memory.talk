# Structure (v5)

v5 的数据模型 —— 描述对象 schema、字段语义、磁盘布局。**是什么**;机制 / 为什么见 [`../../works/v5/`](../../works/v5/README.md),HTTP 契约见 [`../../api/v5/`](../../api/v5/README.md)。

v5 的三层:**task**(做事,裸文件)、**issue**(议事,git)、**card**(记事,git),外加把块变成现场的 **server**。没有数据库、没有索引——磁盘上每个字节都是 canonical。

## 对象清单

| 对象 | 形态 | 存哪 | 文档 |
|---|---|---|---|
| Task | 树上一个节点:目标、项目、父、状态 | `tasks/<id>/task.json` | [task.md](task.md) |
| Canvas / Panel | task 的画布:24×16 网格上的块;**视图,可随时重排** | `tasks/<id>/canvas.json` | [task.md](task.md#canvas) |
| Member | task 的成员 = 一个现场:URI + 认领它的 server;**身份脱离布局** | `tasks/<id>/members.json` | [task.md](task.md#member) |
| Round | agent 成员的会话痕迹,append-only | `tasks/<id>/sessions/<member>/rounds.jsonl` | [task.md](task.md#round) |
| Event | task 自己的时间线,append-only | `tasks/<id>/events.jsonl` | [task.md](task.md#event) |
| Issue / Position / Argument / IssueLink | 问题 + 立场 + 论证 + IBIS 边;立场 / 论证只增不改 | `memory/issues/<id>.json` | [issue.md](issue.md) |
| Card | 维基式事实条目:标题 + 正文 + 语境 + 链接;可改,历史在 git | `memory/cards/<dir>/<slug>.md` | [card.md](card.md) |
| Server / Window / Handle / Live | 认领协议、建现场、交回窗 + 把手 | 不落盘(运行时对象) | [server.md](server.md) |

## ID

| 对象 | 形态 | 示例 |
|---|---|---|
| Task | `task_<UTC 时间戳 14 位><4 hex>` | `task_202609052302072f2f` |
| Member | `<task_id>-m<n>`,task 内顺序编号;**同时是 tmux 会话名** | `task_2026…2f2f-m1` |
| Issue | `iss_<UTC 时间戳 14 位><4 hex>` | `iss_202609052246183f6a` |
| Position / Argument | issue 内顺序编号 `p<n>` / 立场内顺序编号 `a<n>` | `p2`、`a1`;跨对象引用写 `<issue_id>#p2` |
| Card | **仓库内相对路径**(不含 `.md`),目录即分类 | `memory.talk/配置只来自环境变量` |
| Panel | 前端自定,画布内唯一 | `p1` |

前缀 = 类型。card 没有前缀:它就是一条路径,像维基的词条名。

## 三层怎么互相引用

```
Task ──(members)──▶ Member ──(server)──▶ 现场(tmux 会话 / 网页)
  ▲                    │
  │ manager_task       └──(rounds.jsonl)──▶ Round  ◀── Issue.origin / Argument.evidence 指回 (task_id, rounds)
  │ spawned_tasks
Issue ──(card)──▶ Card ──(issue)──▶ Issue          ← 词条 ↔ 讨论页,互指
Issue ──(links)──▶ Issue                            ← IBIS 边
Card  ──(links)──▶ Card                             ← 内链
```

全部是**裸 id 引用,无外键**:task 不知道 issue 的存在(issue 记 `manager_task`,task 侧靠 `GET /api/issues?manager_task=` 反查);card / issue 记的 `task_id` 可以指向已结束甚至已不存在的 task,读时容忍悬挂。

## 磁盘布局速查

```
~/.memory.talk/
├── memory/                      ← git 仓库(认知层 canonical,含全部历史)
│   ├── cards/<dir>/<slug>.md
│   └── issues/<issue_id>.json
└── tasks/<task_id>/             ← 裸文件(现场 canonical,原子写,不进 git)
    ├── task.json
    ├── canvas.json
    ├── members.json
    ├── events.jsonl
    └── sessions/<member_id>/rounds.jsonl
```

完整清单见 [filesystem.md](filesystem.md)。

## 不变性一览

| 对象 | 能不能改 | 历史在哪 |
|---|---|---|
| Card | **能改**(像编辑词条);废弃不删文件 | git log |
| Issue 的 question / origin / created_at | 建后不改 | git log |
| Issue 的 manager_task / card / links | 能改(换绑、写卡、连边) | git log |
| Position / Argument | **只增不改不删** | git log(每条一个 commit) |
| Task 的 goal / project / status | 能改 | events.jsonl(状态变化) |
| Canvas | 能改(全量覆盖,version 乐观锁) | 不留(视图) |
| Member | 建 / 删;`last_attached` 会更新 | events.jsonl |
| Round / Event | **只追加** | 自身就是时间线 |

## 现算、不存的量

| 量 | 在哪算 |
|---|---|
| Position 的 `up` / `down` / `neutral` / `credence` | 读 issue 时从 `arguments[]` 数出来 |
| Member 的 `alive` | 读成员时问 server(`tmux has-session`) |
| Task 树(`children[]`) | 读时从各 `task.json` 的 `parent` 拼出来 |
| Card 目录 | 读时扫 `cards/` 目录树 |
