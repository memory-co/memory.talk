# session

操作 backend 已落库的 session —— **元数据**(`list` / `tag`)+ **逐 round 打注解**(`mark`,v4 新增的抽卡写路径前端)。对话**内容**不在这读,统一走 `memory.talk read <sid>`(`read` 按前缀判型,覆盖 `card_` / `sess_`,以及分片 `card_…#p1` = Position、`sess_…#m1` = mark)。

```
memory.talk session
├── list [filters...] [--limit N] [--json]              # 按多维过滤列 session(只回元数据)
├── tag <sid> [K=V ...] [-K ...] [--json]               # 查 / 加 / 删 session 的 kv 标签
├── mark --session <sid> [--mark <file>] [--json]       # 打注解(给 --mark=文件 / 不给=交互;#…？ 自动建卡)
└── clear-marks <sid> [--json]                          # 清空这个 session 的所有 mark(+ 出处边)
```

需要 server 在跑;CLI 通过 HTTP 调本地端点(`GET /v4/sessions`、`PATCH /v4/sessions/{sid}/tags`、`POST` / `DELETE /v4/sessions/{sid}/marks`)。

## 设计原则

1. **元数据 vs 内容分开**:session 是「原始对话的只读历史」——看内容用 `read`,管标签 / 选条件用 `session list|tag`,打注解抽卡用 `session mark`。
2. **`list` 只回元数据,不回 rounds**:一次列 N 条把全部 rounds 拉回来会爆 payload;列表只看 sid / source / 标签 / cwd / round_count / 时间,看内容用 `read <sid>`。
3. **tag 是 kv 字典**,不是扁平字符串列表(`{"project":"billing","status":"wip"}` 比 `["billing","wip"]` 在过滤时更精确)。
4. **mark 是以写代读**:打注解的首要价值是逼着逐轮真读(防走神),`#…？` 自动建卡是副产物。

---

## session list

按多维条件列 session,**只回元数据**。

```bash
memory.talk session list \
    [--source <name>] [--endpoint <source>@<label>] \
    [--cwd <prefix>] \
    [--tag <expr> ...] \
    [--since <duration|date>] [-d <duration|date>] [--until <duration|date>] \
    [--limit N] [--json]
```

### 过滤参数

| 参数 | 取值 | 说明 |
|---|---|---|
| `--source` | adapter 名(`claude-code` / `codex` / …) | 按 source 卡 |
| `--endpoint` | `<source>@<label>` | 比 `--source` 更细,精确到一个 endpoint |
| `--cwd` | 路径前缀 | 按 `metadata.cwd` 前缀匹配 |
| `--tag` | 见 [`--tag` 操作符](#tag-操作符) | 多个 `--tag` 之间 AND |
| `--since` / `-d` | 持续时长或 ISO 日期 | `created_at >= 起点`;时长语法 `<int><unit>`,unit ∈ `{h,d,w}`(`7d` / `12h` / `2w`)或 ISO `2026-05-01` |
| `--until` | 同上 | `created_at <= 终点` |
| `--limit` | 整数,默认 `20` | 最多返回多少条;按 `created_at` 倒序后截 |

`-d` 是 `--since` 的短选项(跟 `git log --since` 风格一致)。

### `--tag` 操作符

| 表达式 | 语义 |
|---|---|
| `--tag K=V` | key `K` 严格等于 `V` |
| `--tag K!=V` | key `K` **存在且不等于** `V`(严格 NE,**NULL 不命中**;要含「没打 K」再叠 `--tag !K`) |
| `--tag K=V1,V2,V3` | key `K` ∈ `{V1,V2,V3}`(IN) |
| `--tag K` | 有 key `K`(任意值) |
| `--tag !K` | **没有** key `K` |

多个 `--tag` 用 AND;同一 key 给两次不同 eq(`--tag project=a --tag project=b`)合法,**返回空集**(不替你猜矛盾)。当前限制:`K=V1,V2` 的 value 不支持 `,`;无 `LIKE` / 前缀通配;无跨 key `OR`(用 IN 覆盖)。

### 输出 — Markdown(默认)

H3-per-result 块布局(跟 `search` 一致),不用表格:

`````markdown
# session list

`filter: endpoint=claude-code · tag=project=billing` · 23 / 1247 results

---

### [SESSION] `sess-15f0a7fb-…190b0` · claude-code · 47 rounds

`tags: project=billing status=wip` · `cwd: ~/work/billing-svc` · 2026-05-24 09:12 (1 day ago)

---

_(showing 23 of 1247 — pass --limit higher to see more)_
`````

约定:顶行 `# session list`(无 query 概念);第二行给生效过滤条件 + `返回数 / 总数`(没传过滤时只 `N / TOTAL results`,不出 `filter:` 段);每条一个 H3 块、`---` 分隔;标题 `### [SESSION] \`<sid>\` · <source> · <round_count> rounds`(sid 反引号包住便于 copy 给 `read`);标题下一行 metadata(`· ` 分隔):`tags: K=V K=V`(空 tags 整段不出)、`cwd: <path>`(`$HOME`→`~`,超 60 char 中截)、绝对+相对时间 `YYYY-MM-DD HH:MM (X units ago)`;0 命中也出 header;总数 > 返回数时末尾追 `_(showing N of TOTAL — pass --limit higher to see more)_`;不渲染 `metadata.cwd` 以外的 metadata。

### 输出 — JSON(`--json`)

```json
{
  "total": 1247,
  "returned": 23,
  "sessions": [
    {
      "session_id": "sess-15f0a7fb-...190b0",
      "source": "claude-code",
      "endpoint": "claude-code@/home/user/.claude/projects",
      "cwd": "/home/user/work/billing-svc",
      "created_at": "2026-05-24T09:12:03Z",
      "synced_at": "2026-05-24T09:45:11Z",
      "round_count": 47,
      "tags": {"project": "billing", "status": "wip"}
    }
  ]
}
```

---

## session tag

查 / 设 / 删 session 的 kv 标签。**单次可同时设多个 + 删多个**,服务端 PATCH 合并。

```bash
memory.talk session tag <session_id>                              # 查(不传 K=V / -K)
memory.talk session tag <session_id> project=billing status=wip   # 设 / 改
memory.talk session tag <session_id> -status -obsolete            # 删
memory.talk session tag <session_id> project=billing -draft       # 混用
memory.talk session tag <session_id> project=billing --json
```

### 语法

| 形式 | 含义 |
|---|---|
| `K=V` | 设 / 覆盖 key `K` 为 `V`(`V` 整体当字符串存,不做类型推断) |
| `-K` | 删 key `K`(不存在则忽略,不报错) |
| 不传任何 K=V / -K | 只查,输出当前 tags |

约束(违反任一 → 整次拒绝、exit 1、不动 tag):key 匹配 `^[a-zA-Z][a-zA-Z0-9_.-]*$`;value ≤ 200 char;单 session tag ≤ 50;`K=V` 与 `-K` 不能对同一 key 同时出现。

### 输出

Markdown:设 / 删后 `ok: \`<sid>\` · tags = \`project=billing status=wip\``;只查时出一张 `| key | value |` 表;无 tag 输出 `(no tags)`。JSON:`{"session_id": "...", "tags": {...}}`,无论查 / 改都返回**改动后全量 tags**。

---

## session mark

对一个 session **逐 round 打注解**(以写代读,见 [`../../works/v4/session-mark.md`](../../works/v4/session-mark.md))——mark 里 `#…？` 自动建卡 / 关联老卡,出处(`card_source`)精确指那条 mark。**用不用 `--mark` 决定模式**:给 = 文件模式,不给 = 交互模式。

```bash
memory.talk session mark --session <sid> --mark <file>   [--json]   # 给 --mark → 文件模式
memory.talk session mark --session <sid>                 [--json]   # 不给 --mark → 交互模式
```

| 参数 | 必填 | 说明 |
|---|---|---|
| `--session` | 是 | 给哪个 session 打注解;`sess_<...>` |
| `--mark` | 否 | 提交体 YAML 的文件路径。**给了 = 文件模式**(从文件读这个 session 的一批 mark);**不给 = 进交互模式**。`-` 表示从 stdin 读 |
| `--json` | 否 | JSON 输出(默认 Markdown) |

### 提交体(YAML)· 文件模式(`--mark <file>`)

```yaml
last_index: 41          # 乐观锁:提交时我读到的 session 最新 round index
description: 在配 pty、用户突然提 tmux 的那几轮——想搞清他到底要什么
rounds:                 # 从 index 1 起,严格递增,覆盖 ≥90%
  - index: 1
  - index: 2
    comment: 用户要给 pty 配上终端。
  - index: 37
    comment: |
      配 pty 的时候用户突然提了 tmux。#为什么 pty 会让用户想到 tmux？
      他其实想要的是「可重连的会话」,而不是 pty 本身。
  - index: 38           # 读了、没东西标(只占覆盖)
    issues:             # 也可主动声明 issue + 指定 grounding 的轮
      - issue: 可重连会话是不是真需求
        indexes: 37-38
```

> **mark id `m<n>` 由服务端自动分配**——提交体里**不带** id(第一遍 `m1`、第二遍 `m2`…)。
>
> **覆盖率 ≥ 90%(以写代读)**:既然是「以写代读」就得读完整条 session。`rounds` 里 distinct `index` 数必须覆盖 **≥ 90%** 的 round(从 `index: 1` 起逐轮往下),不够 → 整份拒绝(`coverage 23% (12/52 rounds) < 90%`)。没东西标的轮也写一条 `{index}` 占覆盖。

| 字段 | 必填 | 说明 |
|---|---|---|
| `last_index` | 是 | 提交时读到的 session 最新 round index(乐观锁基线 / 总 round 数)。**乐观锁**:与 session 当前最新 round index 不一致 → 整份拒绝([错误](#错误)) |
| `description` | 是 | 这次标注的场景;落进 mark 文件 |
| `rounds` | 是 | 数组,每条 `{index, comment?, issues?}`,**非空**;从 `index: 1` 起、严格递增、不重复 |
| `rounds[].index` | **是** | 这条标注指向第几轮(1-indexed)。**首条必须 1**(从中间起 = 偷跳 → 拒绝) |
| `rounds[].comment` | 否 | 这一轮的感悟。`#…？`(`#` 起、`？`/`?` 止)就地标问题,**grounding 在本轮 `index`**。省略 = 读了没东西标(只占覆盖) |
| `rounds[].issues` | 否 | 主动声明的 issue 数组,每条 `{issue, indexes?}`:`indexes` 指定 grounding 的轮(默认本轮 `index`)。`card_id` / `is_new` 服务端回填,**提交方不给** |

### 交互模式

不喂 YAML 时进入。把 session 当对话**回放**着读:一次摆**当前轮 + 它的上一轮(上下文)**,**从第一轮起**逐轮往前滑、逐轮打标,你边读边把感悟写成 comment。mark id `m<n>` **服务端自动分配**(客户端不配号)。

- 从 `r1` 起逐轮走:第 k 轮渲染**当前轮 `r_k`(标这里)+ 上一轮 `r_{k-1}`(淡色上下文,k=1 时无)**,对当前轮写 comment / 留空 / `:back` / `:q`。走法 `r1`(无上文)→ `r2`(上文 r1)→ … → `r_N`;**每轮都记一条**(空 comment 也记 `{index}`,占覆盖)。

```
$ memory.talk session mark --session sess_def456
session sess_def456 · 41 rounds · interactive step标注(标当前轮 / 回车留空 / :back 回退 / :q 退出)

──────── round 36 ·(上下文)────────
[assistant] 我先帮你把 pty 配上……
──────── round 37 ·(当前 · 标这里)────────
[human] 等等,能不能直接用 tmux?

comment> 配 pty 时用户突然提 tmux。#为什么 pty 会让用户想到 tmux？他其实想要可重连会话。
↵
✓ marked sess_def456 · m1 · 41 round(s)  …  [#37] → new card card_01jz8k2m
```

| 输入 | 作用 |
|---|---|
| 写文本后回车 | 为**当前轮**记一条带 comment 的 round,往前滑一格 |
| 直接回车(空) | 当前轮「读了、没什么可记」→ 记一条 `{index}`(无 comment),往前滑一格——**空 comment 也记进 rounds、算覆盖率** |
| `:back` | 回退一格(看回上一窗口;再走到同一轮会覆盖那一条) |
| `:q` | 退出 |

> **覆盖率门槛**:从第一轮逐轮走到底(每轮写或留空)自然就是 100% 覆盖;若中途 `:q` 时覆盖率 < 90%,提交被**拦下**并提示还差几轮(走完再交),不会半截提交。

`last_index` 进交互时**一次性锁定**;中途 session 又被写了新 round → 下一步提交触发乐观锁、提示退出重进。`description` 进交互时问一次(可空)。mark id 由服务端分配。两种模式落盘完全一致。

### `#…？` → 自动建卡

每条 round 的 `comment` 里的 `#…？`(以及主动声明的 `issues`)在写入时被解析、embed 撞 `cards`(issue)向量库:**miss → 建新卡**(`issue` = 问题文本,还没答案)/ **hit → 关联**老卡;两种都记一条 [`card_sessions`](../../structure/v4/card-session.md),出处 = **`(session_id, mark)`**(即 `sess_<sid>#<mark>`)+ grounding 的 `indexes`(`#…？` 默认 = 本轮 `index`)——精确到那份 mark。判「新 / 老」由**检索**算(miss = 惊讶 = 新卡),不靠 AI 自评。同份 mark 里多轮命中同一张卡 → `card_sessions` 合并成一条(`indexes` 把那几轮并起来)。

### 落地

- 一份 mark → `sessions/<source>/<bucket>/<sid>/marks/m<n>.yaml`(canonical · YAML;`last_index` / `description` / `created_at` / `rounds[]`,每条 round 带 `index` + 可选 `comment` + 回填的 `issues`)。`m<n>` 由服务端分配。
- 元信息 → `session_marks` 表(`session_id` / `mark` / `last_index` / `created_at`),撑乐观锁 + 寻址 + 反查。
- 查看一条 session 的 mark:直接 `read sess_<sid>` —— **session 读取把这条 session 的 marks 折进来**(rounds 之后跟一段 `## marks (N)`,每条一行:`m<n>` · N round(s) · 它的 `#…？` 建/连了哪些卡)。读回某条 mark 的全文走 `read sess_<sid>#m1`(按 `#` 分片判型)。

### 输出

Markdown(默认):

```
✓ marked sess_def456 · m1 · 41 round(s)
  - [#37] #为什么 pty 会让用户想到 tmux？  → new card card_01jz8k2m
```

`--json`:

```json
{
  "session_id": "sess_def456",
  "mark": "m1",
  "rounds": [
    {"index": 1, "issues": []},
    {"index": 37, "comment": "配 pty 时用户突然提了 tmux。#为什么 pty 会让用户想到 tmux？",
     "issues": [{"issue": "为什么 pty 会让用户想到 tmux", "card_id": "card_01jz8k2m", "is_new": true, "indexes": "37"}]}
  ]
}
```

---

## session clear-marks

清空一个 session 的**所有 mark**(`marks/*.yaml` + `session_marks` 行 + `card_sessions` 出处边)。**卡 / Position / review / link 不动**——只走 mark 本身 + 它的出处边。无 mark 删一次是 no-op。

```bash
memory.talk session clear-marks <session_id> [--json]
```

| 参数 | 必填 | 说明 |
|---|---|---|
| `<session_id>` | 是 | 要清空 mark 的 session;`sess_<...>` |
| `--json` | 否 | JSON 输出 |

### 输出

Markdown:`cleared N mark(s) for <sid>`(无 mark → `cleared 0 mark(s) for <sid>`)。
JSON:`{"session_id": "...", "deleted_marks": N}`。

---

## 跟其他命令的边界

| 想做的事 | 用哪条 |
|---|---|
| 看一条 session 的原始对话 + 它上面的 marks | `memory.talk read <session_id>`(rounds + `## marks` 折在一起) |
| 看某条 mark 当时标了啥 / 建了哪些卡 | `memory.talk read sess_<sid>#m1` |
| 给 session 打注解、抽卡 | `memory.talk session mark --session <sid>` |
| 清空一个 session 的所有 mark | `memory.talk session clear-marks <sid>` |
| 按项目 / 状态找 session | `memory.talk session list --cwd … --tag …` |

## 错误

| 情况 | 行为 |
|---|---|
| server 未运行 | `error: cannot reach server`,exit 1 |
| `--source` 未注册 adapter | `error: unknown source 'xxx'`,exit 1 |
| `--since` / `--until` 语法非法 | `error: invalid duration '7days', use '7d' / '12h' / '2w' or ISO date`,exit 1 |
| `tag` / `mark` 的 sid 不存在 | `error: session '<id>' not found`,exit 1 |
| tag key 不合规 / value 太长 / 数量超限 | `error: tag key '<k>' invalid: ...`,exit 1,不动 tag |
| 同时 `K=V` 和 `-K` | `error: cannot both set and unset 'K' in the same call`,exit 1 |
| mark:`last_index` ≠ session 当前最新 round index | `error: session advanced (last_index 41 ≠ current 43); re-read & re-mark`,exit 1(乐观锁 / 409) |
| mark:`rounds` 为空 / YAML 非法 | `error: rounds required` / `error: invalid YAML`,exit 1 |
| mark:首条 index≠1 / 非严格递增 / 越界 | `error: first round index must be 1 …` / `error: round index must be strictly ascending …`,exit 1 |
| mark / clear-marks:sid 不存在 | `error: session '<id>' not found`,exit 1 |

> **状态**:`list` / `tag` / `mark` / `clear-marks` 均**已实现(v1.1.x)**;`mark` 的机制见 [`../../works/v4/session-mark.md`](../../works/v4/session-mark.md)。
