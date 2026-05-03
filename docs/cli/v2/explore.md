# explore

**抽 card 工作台**：以"启动一个 Claude Code 进程"为底层原语,把"翻看历史 session、抽 base card"这件事独立成一个有名字的、可重入的工作流。

memory-talk 自己不抽 card —— 抽 card 是 LLM 的活。explore 做的是把 Claude Code 拉起来 + 把它放进一个**与日常工作目录隔离**的环境里 + 跟踪每次抽取的进度。

跟 [filter](filter.md) / [sync](sync.md) 的关系:

| | 干什么 | 触发频次 |
|---|---|---|
| `sync` | 从 Claude Code 本地导入 session | 自动 / 高频 |
| `filter run new-session` | 列出"还没抽过 card 的 session" | 取景框 |
| `explore` | 启动 Claude Code 抽 card | 用户决定何时干 |

典型链路：`sync` → `filter run new-session` 拿到 ids → `explore auto` 让 LLM 自己抽 → `filter mark new-session <ids>` 把已处理的从框里调走。

## 为什么单独搞个目录

Claude Code 有个**根据 cwd 决定 project_id** 的特性:同一个目录下起的每次 `claude` 都共享一个 project 命名空间。这条特性带来一个直接的好处:explore 工作流的所有 session 全都落在同一个 project 下,跟用户日常项目 session **物理隔离**。

更关键的是 **recall hook 不该在这里触发**。日常工作目录里,`UserPromptSubmit` 这类 hook 会自动跑 [recall](recall.md) 把记忆塞进 LLM context —— 这是"工作时被记忆动态补全"的场景。explore 是反过来:**用户主动来翻记忆抽 card**,不需要 recall 再塞一次,塞了反而搅乱思路。

所以 explore cwd 是个"hook 真空区":

- claude 起在这里 → 不打 recall
- claude 抽出来的 card 通过 `memory-talk card create` 工具调用入库 —— 这条路不绕开 hook 配置(没有这种 hook),走 HTTP API 落到主 db,跟在哪儿抽的无关

## settings.json

```json
{
  "explore": {
    "cwd": "~/.memory-talk/explore"
  }
}
```

| 字段 | 默认 | 说明 |
|---|---|---|
| `explore.cwd` | `~/.memory-talk/explore` | Claude Code 启动目录。绝对路径或 `~/` 起头。 |

setup wizard 跑首次安装时会:

1. `mkdir -p <explore.cwd>` —— 创建空目录
2. 在 `<explore.cwd>/.claude/settings.json` 写一份**只对该目录生效的 hook 覆盖**:把全局 / 用户级 recall hook 显式置空
3. 摘要里报告"explore 目录已就绪"

已存在的 explore 目录不动 —— setup 是幂等的。

## 子命令

```
memory-talk explore
├── list                                # 列出已有探索记录
├── detail <session_id>                 # 查看某条记录
├── auto [--limit N]                    # 自动跑一次抽取(claude -p,non-interactive)
├── manual                              # 进入 claude code(交互)
└── resume <session_id>                 # 续上某次记录(交互)
```

所有子命令支持 `--data-root PATH` 和 `--json`。

### explore list

```bash
memory-talk explore list [--limit N] [--json]
```

枚举 explore cwd 下所有 Claude Code session(直接读 `~/.claude/projects/<explore-project-id>/*.jsonl`,**不经过 sync**)。

**Markdown:**

```markdown
# explore (3)

| session_id | started | rounds | cards | status |
|---|---|---|---|---|
| `sess_01k...` | 2026-05-03 10:24 | 14 | 3 | done |
| `sess_01j...` | 2026-05-02 22:11 | 6 | 0 | abandoned |
| `sess_01h...` | 2026-04-30 14:00 | 28 | 7 | done |
```

字段:

- `cards`:本 session 里通过 `memory-talk card create` 创建的 card 数(扫 session 的 tool_use round 算出)
- `status`:`done`(最后一轮 > 30 分钟前)/ `active`(< 30 分钟,可能还在跑)/ `abandoned`(rounds < 3 且超过 1 小时没动)—— 纯粹基于时间戳的启发,没有真正的状态机

**JSON:**

```json
{
  "explore_cwd": "/home/me/.memory-talk/explore",
  "records": [
    {"session_id": "sess_01k...", "started_at": "2026-05-03T10:24:00Z",
     "rounds": 14, "cards": 3, "status": "done"}
  ]
}
```

### explore detail

```bash
memory-talk explore detail <session_id> [--json]
```

打开某条记录的详细视图:

- session 的基本信息(rounds, started_at, last_at)
- 这次抽出来的 card 列表(`card_id` + `summary` + 创建时的轮次)
- session 的 tag(包括自动打的 `explore` / `sync_session`)
- 文件路径(本地 jsonl 路径,方便用户用别的工具看原始内容)

跟 `memory-talk view sess_xxx` 的差异:explore detail **聚焦于本次抽取产出**(cards + 抽取流程),不展开 round 内容。要看完整对话用 `view`。

### explore auto

```bash
memory-talk explore auto [--limit N] [--json]
```

非交互式跑一次抽取:`claude --print` 在 explore cwd 起,内置 prompt 引导它:

1. 读 `new-session` filter 的 subject_ids
2. 对每条 session,调 `memory-talk view <sid>` 看内容
3. 识别"值得固化"的判断 / 经验 / 决策,调 `memory-talk card create` 写 card
4. 全部抽完后调 `memory-talk filter mark new-session <sids>`
5. 输出本次抽了几条 card

参数:

| 参数 | 默认 | 说明 |
|---|---|---|
| `--limit` | 全部 | 上限,避免一次抽得太多。filter 给了 50 条但只想抽 5 条 → `--limit 5`。 |

**阻塞式**:全程等 claude 跑完才返回。`Ctrl-C` 会杀掉子进程。

**Markdown 输出**(命令结束后一次性打印):

```markdown
# explore auto · **ok**

| field | value |
|---|---|
| candidates | 12 |
| limit | 5 |
| processed | 5 |
| cards_created | 3 |
| session_id | `sess_01k...` |
| duration | 4m 17s |
```

**JSON:**

```json
{
  "status": "ok",
  "candidates": 12,
  "limit": 5,
  "processed": 5,
  "cards_created": 3,
  "session_id": "sess_01k...",
  "duration_sec": 257
}
```

failure 模式:

- `claude` 命令找不到 → exit 1,提示安装
- claude 退出码非 0 → 透传退出码,把它的 stderr 转发出来
- 内置 prompt 模板缺 → 包损坏,exit 1

### explore manual

```bash
memory-talk explore manual
```

`exec claude`(进程替换,不是 subprocess):

```bash
cd <explore.cwd> && exec claude
```

用户落进 claude 交互界面,自己决定看什么、抽什么。**memory-talk 进程在这一刻被 claude 替换** —— 退出 claude 等于退出整个命令。

不接 `--json` —— 这条命令本质上不返回结构化数据,它就是个跳板。

### explore resume

```bash
memory-talk explore resume <session_id>
```

续上之前某次记录,等价于:

```bash
cd <explore.cwd> && exec claude --resume <session_uuid>
```

`<session_id>` 接 `sess_` 前缀的 memory-talk id 或 Claude Code 原始 UUID 都行(命令内部去前缀)。session 必须确实在 explore cwd 下 —— 不在则报错(避免误把工作 session 拉进来 resume,污染 explore namespace)。

跟 manual 一样,exec 替换进程,不接 `--json`。

## 跟 sync / tag 的联动

- 每次 explore 跑完(无论 auto / manual / resume),session 文件已经在 Claude Code 本地 —— 下次 `memory-talk sync` 自动导入
- sync 路径检测到 session 来自 `explore.cwd` → **自动打 `explore` tag**(类似 `sync_session` 那套机制)
- explore session 同样会被 `sync_session` 打 tag —— 但通常你不会想让 explore session 自己又出现在 `new-session` filter 里(那会形成"抽 explore session 的 explore session" 套娃),所以内置 `new-session` filter 的 query 在 v0.4.2 之后会演进成排除 `tag = "explore"`(详见 filter.md)

## hook 隔离机制

memory-talk 不管 Claude Code 的 hook 配置 —— 那是 Claude 工具的事。**explore 的隔离靠 Claude Code 自己的 project-local settings 优先级**:

```
~/.memory-talk/explore/.claude/settings.json   ← 最高优先级,完全覆盖
~/.claude/settings.json                         ← user-level,默认源
```

setup wizard 在 `<explore.cwd>/.claude/settings.json` 写:

```json
{
  "hooks": {
    "UserPromptSubmit": []
  }
}
```

(`hooks.UserPromptSubmit = []` 是显式空数组,**覆盖**用户级配置而不是合并。)

如果用户自己改了这份文件、或干脆删掉 —— 那是用户的选择,memory-talk 不再校正。`memory-talk setup` 重跑时会**询问**是否复原(默认 yes)。

## 为什么 manual / resume 走 exec 而不是 subprocess

两个原因:

1. **TTY ownership**:claude 是 TUI,需要直接拥有 tty。subprocess 包一层会让信号转发(SIGWINCH / SIGINT)和原始 escape sequence 处理变怪,resize 终端会出问题
2. **进程模型清晰**:用户 `Ctrl-C` 退 claude 时直接退到 shell,而不是先回到 memory-talk 然后再退一次 —— 后者会让人疑惑"这个 wrapper 还在做什么"

代价:exec 之后 memory-talk 没法在 claude 退出后做 post-processing(比如自动 sync)。这条**故意**留给用户:`exit` 后想 sync 就 `memory-talk sync`,想接着抽就再 `explore`。explore 不替用户决定何时落库。

## 错误

| 情况 | 行为 |
|---|---|
| `<explore.cwd>` 不存在 | exit 1,提示跑 `memory-talk setup` |
| `<explore.cwd>` 不是目录(是文件 / 软链坏了) | exit 1 |
| `claude` 不在 PATH(auto / manual / resume) | exit 1,提示安装 Claude Code |
| `resume <id>` 但 id 对应 session 不在 explore cwd | exit 1,提示"这条 session 不属于 explore 命名空间" |
| `auto` 中 claude 进程被信号杀掉 | 透传 exit code(130 = SIGINT,143 = SIGTERM) |
| `auto` 跑时 `new-session` filter 不存在(用户删了内置 filter) | exit 1 |

## 推荐姿势

```bash
# 日常 sync,看下框里有没有积压
memory-talk sync
memory-talk filter run new-session

# 框里有 5 条,让 LLM 自动抽
memory-talk explore auto --limit 5

# 看看抽了啥
memory-talk explore list

# 想自己抽 / 想复盘某条 session 的抽取过程
memory-talk explore manual
# (在 claude 里)/exit
memory-talk explore list             # 看刚才的记录
memory-talk explore resume sess_01k...  # 接着抽
```

## 设计取舍

### 为什么 explore 不直接调 LLM API,而是非要包一层 Claude Code

memory-talk 的 [架构原则](../../../CLAUDE.md) 是 **Python 代码不调 LLM API**。所有认知工作都通过 Skill / agent 框架转交 LLM。explore 也不破这条 —— 它**不**直接 OpenAI / Anthropic API,只起 `claude` 进程,让 Claude Code 自己用工具(`memory-talk view` / `memory-talk card create`)完成抽取。

直接调 API 也不是不行,但那样 explore 自己就要管 prompt / context window / tool_use loop,等于把 Claude Code 的核心机制重做一遍。借 claude 已有的 agent loop 是更轻的实现,而且用户能看到 claude 的全流程(每一轮都在 jsonl 里),debug 友好。

### 为什么 list / detail 直接读 jsonl,不走 memory-talk db

为了**不依赖 sync**。用户跑完 `explore manual` 想立刻看刚才抽的 card,不应该被"先 sync 一下"卡住。explore list / detail 拿原始 jsonl 拼出来,sync 之后再走 `memory-talk view` / `log` 看完整视图。

代价:list 出来的 `cards` 计数是从 jsonl 里扫 tool_use 数出来的,不是真"db 里的 card 数"——如果 claude 调 `card create` 但服务器侧失败了(罕见),这两个数会差。我们认它,因为 explore list 的目标是"快速反馈这次跑了啥",精确数据看 sync 后的 db。

### 为什么 auto 阻塞而不是后台

抽 card 是个**用户主动决定的动作**,不是后台守护。每次跑预期几分钟到十几分钟,跟 sync 量级类似。塞后台只会让用户"我跑了吗?抽完了吗?"反复检查,不如全程在终端里看着 claude 输出。

