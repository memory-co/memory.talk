# explore

**LLM 主导的卡维护工作台**:在一个隔离环境里启动 Claude Code,让它读会话、抽新卡或给老卡(答案)写 review。memory.talk 自己不抽不评 —— 抽 / 评是 LLM 的活,explore 负责**拉起 claude + 隔离 + 跟踪产出**。

> **v4 产物差异**:抽出来的不再是一张 insight 卡(一句陈述),而是一张 **v4 卡**(一个问题 Issue + 若干答案 Position)。抽卡的写路径走 [`session mark`](session.md#session-mark) —— 在 explore 目录里逐 round 打注解,mark 里 `#…？` 就地标问题、写入时自动建卡 / 关联老卡。工作台的拉起 / 隔离 / 跟踪机制本身照 v3。

| | v3 explore 产物 | v4 explore 产物 |
|---|---|---|
| 抽出来的是 | 一张 insight 卡(一句陈述 + rounds + stats) | 一张 **v4 卡**(一个问题 Issue + 若干答案 Position) |
| 写入路径 | v3 探洞见 | [`session mark`](session.md#session-mark)(逐 round 注解,`#…？` 自动建 v4 卡) |

机制(cwd 隔离 + recall hook 真空区 + 无独立工作队列)详见 [`../../works/v3/explore-cwd-suppression.md`](../../works/v3/explore-cwd-suppression.md)。

`settings.explore.cwd` 默认 `~/.memory.talk/explore`,由 setup wizard 创建。详见 [setup.md](setup.md)。

## 子命令

```
memory.talk explore
├── pending [--limit N]                 # 候选队列:未被任何卡引用过的 work session
├── list [--limit N]                    # 产出历史:explore namespace 下已跑过的 session
├── detail <session_id>                 # 单条 explore session 详情(产出的 cards / reviews)
├── auto [--limit N]                    # 非交互式:claude -p 自动消费 pending
├── manual                              # 进入 claude(交互式)
└── resume <session_id>                 # 续接某条 explore 记录(交互式)
```

适用的命令支持 `--json`。**所有读路径都走 backend HTTP**,所有 namespace 判断都走 `metadata.cwd` 前缀匹配,不直接读 `~/.claude/projects/*.jsonl`。

> data root **固定在 `~/.memory.talk`**(不暴露 `--data-root` 参数)。后续如需配置,会在 [setup](setup.md) 里加入,其它命令不动。

### explore pending

```bash
memory.talk explore pending [--limit N] [--json]
```

后端定义:

> `pending = { session | NOT EXISTS(card 引用 session.id) AND session.metadata.cwd NOT startswith <explore.cwd> AND session.last_at <= now - 30min }`

三条规则:
- **未被引用**:还没有任何卡引用过这条 session
- **不是 explore 自己产出的**:排除 `<explore.cwd>` 下的 session(避免"抽 explore session 套娃")
- **最近一轮 ≥ 30 分钟前**:可能还在跑的 session 暂不进队列(`last_at` 在 30 分钟内的算"active",pending 不取)

**Markdown:**

````markdown
# pending (5)

| session_id | started | last_at | rounds | cwd |
|---|---|---|---|---|
| `sess_01k...` | 2026-05-12 14:24 | 2026-05-12 17:11 | 28 | `/home/me/proj-a` |
| `sess_01j...` | 2026-05-11 09:33 | 2026-05-11 11:02 | 12 | `/home/me/proj-b` |
````

**JSON:**

```json
{
  "count": 5,
  "sessions": [
    {"session_id": "sess_01k...", "started_at": "2026-05-12T14:24:00Z",
     "last_at": "2026-05-12T17:11:00Z", "rounds": 28, "cwd": "/home/me/proj-a"}
  ]
}
```

> **pending 的"未被引用"是严格的**:有 1 张卡引用过这条 session,这条 session 就出队 —— 即便里面还有更多问题没抽完。要重访 / 二次抽取,直接 `memory.talk read <sid>` + [`session mark`](session.md#session-mark) 即可,不靠 pending 推回来。

### explore list

```bash
memory.talk explore list [--limit N] [--json]
```

列出 **`metadata.cwd` startswith `<explore.cwd>`** 的所有 session —— 即 explore 自己跑出来的 session 历史。

**Markdown:**

````markdown
# explore (3)

| session_id | started | rounds | cards | reviews | status |
|---|---|---|---|---|---|
| `sess_01k...` | 2026-05-03 10:24 | 14 | 3 | 1 | done |
| `sess_01j...` | 2026-05-02 22:11 | 6 | 0 | 0 | abandoned |
| `sess_01h...` | 2026-04-30 14:00 | 28 | 7 | 4 | done |
````

字段定义(全部从 backend 实时算,不存):

- `cards`:本 session 产出的 v4 卡数
- `reviews`:本 session 产出的 review 数
- `status`(按时间戳的弱启发,仅显示用):
  - `active`:`last_at` 距今 < 30 分钟
  - `done`:`last_at` 距今 ≥ 30 分钟 **且** `cards + reviews > 0`
  - `abandoned`:`last_at` 距今 ≥ 1 小时 **且** `cards + reviews = 0`
  
  `abandoned` 仅是个显示标签,**backend 不据此清理任何数据** —— session 始终留着。

### explore detail

```bash
memory.talk explore detail <session_id> [--json]
```

走 backend,聚焦**本 session 的产出**:

- session 基本信息(`started_at` / `last_at` / `rounds` / `cwd` / `status`)
- 产出的卡列表(每条 `card_id` + `issue` + `created_at`)
- 产出的 review 列表(每条 `review_id` + 关联的 `position_id` + `argument` + `comment` + `indexes`)

跟 `memory.talk read sess_xxx` 的差别:detail **不展开 round 内容**;要看对话原文用 `read`。

### explore auto

```bash
memory.talk explore auto [--limit N] [--json]
```

非交互式跑一次:`claude --print` 在 `<explore.cwd>` 起,内置 prompt 让它:

1. 调 `memory.talk explore pending --limit N --json` 拿候选 session
2. 对每条候选:
   - `memory.talk read <sid>` 看内容
   - 决定**三选一**:
     - **抽卡**(找到值得固化的新问题 / 答案)→ 逐 round 走 [`session mark`](session.md#session-mark)(`#…？` 自动建卡 / 加答案)
     - **写 review**(内容反驳 / 支持某张卡的某个答案)→ `memory.talk card review --position <pid> ...`
     - **跳过**(纯闲聊 / 已在别处沉淀)
3. 处理完进下一条,直到队列空或达上限
4. stdout 输出 summary

参数:

| 参数 | 默认 | 说明 |
|---|---|---|
| `--limit` | `settings.explore.auto_default_limit`(默认 5) | 上限。pending 给了 50 条但只想抽 5 条 → `--limit 5`。 |

**阻塞执行**:全程等 claude 跑完才返回。`Ctrl-C` 杀子进程,**已落库的 card / review 不回滚**(backend append-only,落了就在)。

**Markdown 输出**(claude 跑完后一次性打印):

````markdown
# explore auto · **ok**

| field | value |
|---|---|
| candidates | 12 |
| limit | 5 |
| processed | 5 |
| cards_created | 3 |
| reviews_created | 2 |
| skipped | 1 |
| session_id | `sess_01k...` |
| duration | 4m 17s |
````

`session_id` 是**本次 claude 自己跑出来的 session 的 id**,可以走 `explore detail <sid>` 看完整决策过程。

**JSON:**

```json
{
  "status": "ok",
  "candidates": 12,
  "limit": 5,
  "processed": 5,
  "cards_created": 3,
  "reviews_created": 2,
  "skipped": 1,
  "session_id": "sess_01k...",
  "duration_sec": 257
}
```

failure 模式:
- `claude` 不在 PATH → exit 1,提示安装
- claude 退出码非 0 → 透传退出码,把它的 stderr 转发
- 内置 prompt 模板缺失 → 包损坏,exit 1
- pending 为空 → **不起 claude**,直接 ok 退,`processed=0`

### explore manual

```bash
memory.talk explore manual
```

进程替换:

```bash
cd <explore.cwd> && exec claude
```

用户落进 claude 交互界面,自己决定看什么、抽什么、评什么。**memory.talk 进程被 claude 替换** —— 退出 claude = 退出整个命令。不接 `--json`。

### explore resume

```bash
memory.talk explore resume <session_id>
```

续接某条 explore 记录,等价于:

```bash
cd <explore.cwd> && exec claude --resume <claude_uuid>
```

`<session_id>` 接 `sess_<uuid>`(memory.talk id)或裸 UUID 都行,内部去前缀。

**namespace 校验**:CLI 先调 backend 拉这条 session 的 `metadata.cwd`,确认 startswith `<explore.cwd>`;不通过则报错 —— 避免误把工作 session 拉进 explore namespace(否则 list / detail 会把它算成 explore 产出,污染统计)。

不接 `--json`。

## hook 隔离机制

memory.talk 不管 Claude Code 的 hook 配置,**靠 Claude Code 自己的 project-local settings 优先级**:

```
<explore.cwd>/.claude/settings.json    ← 最高优先级,完全覆盖
~/.claude/settings.json                ← user-level,默认源
```

setup 写的覆盖文件内容:

```json
{
  "hooks": {
    "UserPromptSubmit": []
  }
}
```

显式空数组 → 覆盖 user-level 配置,不合并。

用户自己改了 / 删了这份文件 —— memory.talk 不再校正,只在 setup 重跑时**询问**是否复原(默认 yes)。

## 错误

| 情况 | 行为 |
|---|---|
| `<explore.cwd>` 不存在 | exit 1,提示跑 `memory.talk setup` |
| `<explore.cwd>` 不是目录(文件 / 软链坏) | exit 1 |
| `claude` 不在 PATH | exit 1,提示安装 Claude Code |
| `resume <id>` 但 backend 查到 cwd 不在 explore namespace | exit 1,"这条 session 不属于 explore 命名空间" |
| `resume <id>` 但 backend 查不到这条 session | exit 1,"sync 还没追上 / id 打错" |
| `auto` 中 claude 进程被信号杀掉 | 透传 exit code(130=SIGINT, 143=SIGTERM)|
| `auto` 跑时 pending 为空 | 不起 claude,ok 退,`processed=0` |
| backend(server)未运行 | exit 1,提示先 `memory.talk server start` |

## 推荐姿势

```bash
# 看看积压
memory.talk explore pending

# 让 LLM 自动消费前 5 条
memory.talk explore auto --limit 5

# 看刚才抽 / 评了啥
memory.talk explore list
memory.talk explore detail sess_01k...

# 自己抽 / 复盘
memory.talk explore manual
# (在 claude 里) /exit
memory.talk explore resume sess_01k...  # 接着上次接着抽
```

## 设计取舍

### 为什么 explore 不直接调 LLM API,而是包一层 Claude Code

架构原则(`CLAUDE.md`):Python 不调 LLM API,认知工作走 Skill / agent。explore 也不破这条 —— 不直连 OpenAI / Anthropic API,只起 `claude` 进程,让它用工具(`memory.talk read` / `session mark` / `card review`)完成抽取 + 评价。

直接调 API 也能跑,但 explore 自己要管 prompt / context window / tool_use loop,等于把 Claude Code 的 agent 核心机制再做一遍。借 claude 已有的 agent loop 是更轻的实现,而且全流程都落 backend(`explore detail` 能拉出完整对话),debug 友好。

### 为什么 namespace 走 cwd 而不是任何 tag / 状态字段

cwd 是 Claude Code **原生**的 project 分桶机制 —— 同一目录下起的所有 claude 共享 project_id。explore 只是消费这条已有信号,不重造一套 "explore session" 元数据。

整体也不依赖 tag / 状态字段做 namespace 判断,走 `metadata.cwd` 前缀匹配是跟这条原则一致的选择。

### 为什么 pending 是"严格未引用",不是"未处理"

定义严格简单:**有 1 张卡引用过这条 session,这条 session 就出 pending**。即便里面还有问题没抽。

理由:
- **简单**:一条 SQL 推得,无 cursor、无 checkpoint、无 state file。
- **"被关注过一次"=核心已被 LLM 看过**:后续要不要再回来,是人 / agent 的判断,不应该由队列机制强行推。
- **真有"忘抽了"**:`read <sid>` + [`session mark`](session.md#session-mark) 直接补,代价微小。

如果以后想要"按 last_at 排序 + 已被引用过但有新内容"这种更聪明的队列,做成 `explore pending --include-revisits` 扩展,**不进默认行为**。

### 为什么 list / detail / pending / resume 都走 backend

sync 是后端实时 watcher,落 backend 跟 jsonl 落盘几乎同时,旁路读 jsonl 没必要。

走 backend 的好处:
- **单一数据源**:explore CLI 不需要知道 `~/.claude/projects/` 路径细节,也不需要复刻 Claude Code 的 project_id 派生逻辑
- **精确 stats**:cards / reviews 计数走 backend SQL,准确
- **namespace 校验干净**:resume 时直接 backend 查 metadata,不读文件系统

代价是依赖 `server` 在跑。所有读路径都依赖 backend,explore 没理由特殊。

### 为什么 manual / resume 走 exec 而不是 subprocess

1. **TTY ownership**:claude 是 TUI,subprocess 包一层会让信号转发(SIGWINCH / SIGINT)和 escape sequence 处理变怪。
2. **进程模型清晰**:`Ctrl-C` 退 claude 直接退到 shell,而不是先回到 memory.talk 再退一次。

代价:exec 之后没法做 post-processing。**故意留着** —— sync 是实时的,resume 期间想看进度直接开第二个终端 `memory.talk explore list` 即可。

### 为什么 auto 阻塞而不是后台

抽卡 / 写 review 是**用户主动决定的动作**,不是后台守护。每次几分钟到十几分钟。塞后台只让用户反复检查"我跑了吗?抽完了吗?",不如全程在终端看着 claude 输出。
