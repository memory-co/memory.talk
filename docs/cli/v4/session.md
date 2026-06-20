# session

操作 backend 已落库的 session —— **元数据**(`list` / `tag`)+ **逐 round 打注解**(`mark`,v4 新增的抽卡写路径前端)。对话**内容**不在这读,统一走 `memory.talk read <sid>`(`read` 按前缀判型,覆盖 `card_` / `sess_`,以及分片 `card_…#p1` = Position、`sess_…#m1` = mark)。

```
memory.talk session
├── list [filters...] [--limit N] [--json]              # 按多维过滤列 session(只回元数据)
├── tag <sid> [K=V ...] [-K ...] [--json]               # 查 / 加 / 删 session 的 kv 标签
└── mark --session <sid> [--mark <file>] [--json]       # 打注解(给 --mark=文件 / 不给=交互;#…？ 自动建卡)
```

需要 server 在跑;CLI 通过 HTTP 调本地端点(`GET /v4/sessions`、`PATCH /v4/sessions/{sid}/tags`、`POST /v4/sessions/{sid}/marks`)。

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
marks:
  - id: m1
    indexes: 36-37        # 这条的 #…？ 从哪几轮读出来的(含 #…？ 必给)
    mark: |
      配 pty 的时候用户突然提了 tmux。#为什么 pty 会让用户想到 tmux？
      他其实想要的是「可重连的会话」,而不是 pty 本身。
  - id: m2
    mark: 这段其实在排查 EMFILE,跟句柄上限有关。
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `last_index` | 是 | 提交时读到的 session 最新 round index。**乐观锁**:与 session 当前最新 round index 不一致 → 整份拒绝([错误](#错误)) |
| `description` | 是 | 这次标注的场景;随每条 mark 落盘 |
| `marks` | 是 | 数组,每条 `{mark: <文本>}`,**非空**。`mark` 里 `#…？`(`#` 起、`？`/`?` 止)就地标问题 |
| `marks[].id` | **是** | mark id `m<n>`,**每条显式给、不默认分配**;session 内单调、不跳号 / 不复用(续标接着上次最大序号) |
| `marks[].indexes` | **含 `#…？` 时必给** | 这条 mark 的 `#…？` grounding 的 round(s)(问题从哪几轮读出来的;可多个,`36-37` / `3,7,12`)→ 落 `card_sessions.indexes`。**交互模式自动填当前标注轮的 index**(单轮 `37`,上一轮只作上下文);无 `#…？` 的 mark 不需要 |

### 交互模式

不喂 YAML 时进入。把 session 当对话**回放**着读:一次摆**当前轮 + 它的上一轮(上下文)**,逐轮往前滑、逐轮打标,你边读边把感悟写成 mark(**session 级、不绑单一 round**)。**每个 round 都可标**(含第一轮);上一轮只是给你语境,有就显示、没有(第一轮)就只摆当前轮。

- 从 `r1` 起逐轮走:第 k 轮渲染**当前轮 `r_k`(标这里)+ 上一轮 `r_{k-1}`(淡色上下文,k=1 时无)**,对当前轮写 mark / 跳过 / `:back` / `:q`。走法 `r1`(无上文)→ `r2`(上文 r1)→ … → `r_N`(上文 r_{N-1});**每轮都能标**。

```
$ memory.talk session mark --session sess_def456
session sess_def456 · 41 rounds · 交互打标(标当前轮 / 回车跳过 / :back 回退 / :q 退出)

──────── round 36 ·(上下文)────────
[assistant] 我先帮你把 pty 配上……
──────── round 37 ·(当前 · 标这里)────────
[human] 等等,能不能直接用 tmux?

mark> 配 pty 时用户突然提 tmux。#为什么 pty 会让用户想到 tmux？他其实想要可重连会话。
↵
✓ sess_def456#m1 · round 37 · → new card card_01jz8k2m  (#为什么 pty 会让用户想到 tmux？)
```

| 输入 | 作用 |
|---|---|
| 写文本后回车 | 为**当前轮**落一条 mark,往前滑一格 |
| 直接回车(空) | 当前轮跳过(不落 mark),往前滑一格 |
| `:back` | 回退一格(看回上一窗口;已落的 mark 不撤,append-only) |
| `:q` | 退出 |

`last_index` 进交互时**一次性锁定**;中途 session 又被写了新 round → 下一步提交触发乐观锁、提示退出重进。`description` 进交互时问一次(可空)。两种模式落盘完全一致。

### `#…？` → 自动建卡

每条 `mark` 文本里的 `#…？` 在写入时被解析、embed 撞 `cards`(issue)向量库:**miss → 建新卡**(`issue` = 问题文本,还没答案)/ **hit → 关联**老卡;两种都记一条 [`card_sessions`](../../structure/v4/card-session.md),出处 = **`(session_id, mark)`**(即 `sess_<sid>#<mark>`)——精确到那条 mark。判「新 / 老」由**检索**算(miss = 惊讶 = 新卡),不靠 AI 自评。

### 落地

- 每条 mark → `sessions/<source>/<bucket>/<sid>/marks/m<n>.yaml`(canonical · YAML;`last_index` / `description` / `mark` / `issues` / `created_at`)。
- 元信息 → `session_marks` 表(`session_id` / `mark` / `last_index` / `created_at`),撑乐观锁 + 寻址 + 反查。
- 读回某条 mark 走 `read sess_<sid>#m1`(按 `#` 分片判型)。

### 输出

Markdown(默认):

```
✓ marked sess_def456 · round 37 · last_index 41
  m1  #为什么 pty 会让用户想到 tmux？  → new card card_01jz8k2m
  m2  (无问题)
```

`--json`:

```json
{
  "session_id": "sess_def456",
  "last_index": 41,
  "marks": [
    {"mark": "m1", "issues": [{"issue": "为什么 pty 会让用户想到 tmux", "card_id": "card_01jz8k2m", "is_new": true, "indexes": "36-37"}]},
    {"mark": "m2", "issues": []}
  ]
}
```

---

## 跟其他命令的边界

| 想做的事 | 用哪条 |
|---|---|
| 看一条 session 的原始对话 | `memory.talk read <session_id>` |
| 看某条 mark 当时标了啥 / 建了哪些卡 | `memory.talk read sess_<sid>#m1` |
| 给 session 打注解、抽卡 | `memory.talk session mark --session <sid>` |
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
| mark:`marks` 为空 / YAML 非法 | `error: marks required` / `error: invalid YAML`,exit 1 |
| mark:`id` 缺失 / 跳号 / 复用 | `error: mark id required and must be monotonic (m<n>)`,exit 1 |

> **状态**:`list` / `tag` / `mark` 均**已实现(v1.1.x)**;`mark` 的机制见 [`../../works/v4/session-mark.md`](../../works/v4/session-mark.md)。
