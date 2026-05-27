# session

操作 backend 已落库的 session 元数据 —— 不读对话内容,**对话内容统一走 `memory.talk read <sid>`**(同一个 read 命令覆盖 card / session / review 三种 id,session 不再单独开一条读路径)。

```
memory.talk session
├── list [filters...] [--limit N] [--json]    # 按多维过滤列出 session
└── tag <sid> [K=V ...] [-K ...] [--json]     # 查 / 加 / 删 session 上的 kv 标签
```

需要 server 在跑;CLI 通过 HTTP 调 `GET /v3/sessions` + `PATCH /v3/sessions/<sid>/tags`(详见 [`../../api/v3/sessions.md`](../../api/v3/sessions.md))。

## 设计原则

1. **元数据 vs 内容分开**。session 是"原始对话的只读历史"—— 看内容用 `read`,管标签 / 选条件用 `session`。两条命令的关注点不混。
2. **tag 是 key-value 字典,不是扁平字符串列表**。原因:用户场景里 tag 经常带语义("这是哪个项目"、"什么状态"),flat list 没法表达 key 维度。`{"project": "billing", "status": "wip"}` 比 `["billing", "wip"]` 在过滤时更精确(`--tag project=billing` 不会误命 `--tag status=billing`)。
3. **`session list` 只列元数据,不返回 rounds**。一次列 N 条 session,把每条的全部 rounds 也拉回来会爆 payload —— 列表只看 sid / source / 标签 / cwd / round_count / 时间。要看具体对话用 `read <sid>` 单条展开。
4. **v3 当初删 tag 是因为 card 没必要;session 加回 tag 不冲突**。card 的归类已经被 `source_cards` lineage 和论坛动力学(review + 排序)承担,不需要 tag。session 没有这两层,要做"按项目分组 / 标 WIP"必须有一个轻量标签机制 —— 这次只把 session 的 tag 加回来,**card 维持无 tag**(参见 [`talk-card.md`](../../structure/v3/talk-card.md))。

## 子命令

### session list

按多维条件列 session,**只回元数据**(对话内容用 `read`)。

```bash
memory.talk session list \
    [--source <name>] [--endpoint <source>@<label>] \
    [--cwd <prefix>] \
    [--tag <expr> ...] \
    [--since <duration|date>] [-d <duration|date>] \
    [--until <duration|date>] \
    [--limit N] [--json]
```

#### 过滤参数

| 参数 | 取值 | 说明 |
|---|---|---|
| `--source` | adapter 名(`claude-code` / `codex` / …) | 按 source 卡 |
| `--endpoint` | `<source>@<label>` | 比 `--source` 更细,精确到一个 endpoint。0.7.x 多 endpoint 后用 |
| `--cwd` | 路径前缀 | 按 `metadata.cwd` 前缀匹配(复用 [explore namespace](explore.md) 同款逻辑) |
| `--tag` | 5 种表达式,见 [`--tag` 操作符](#tag-操作符) | 多个 `--tag` AND 串接 |
| `--since` / `-d` | 持续时长或 ISO 日期 | session `created_at >= 起点`;`7d` / `12h` / `2w` / `2026-05-01` |
| `--until` | 同上 | session `created_at <= 终点` |
| `--limit` | 整数,默认 `20` | 最多返回多少条;按 `created_at` 倒序后截 |

`--since` / `--until` duration 语法:`<int><unit>`,unit ∈ `{h, d, w}`(小时 / 天 / 周)。`-d` 是 `--since` 的短选项(高频用法,跟 `git log --since` 风格一致)。

#### `--tag` 操作符

| 表达式 | 语义 |
|---|---|
| `--tag K=V` | tag 的 key `K` 严格等于 `V` |
| `--tag K!=V` | tag 的 key `K` **存在且不等于** `V`(严格 NE,**NULL 不算命中**;要把"没打 K"也包含进去再叠一个 `--tag !K`) |
| `--tag K=V1,V2,V3` | tag 的 key `K` ∈ `{V1, V2, V3}`(IN,覆盖 OR 场景) |
| `--tag K` | tag 里有 key `K`(任意值) |
| `--tag !K` | tag 里**没有** key `K` |

多个 `--tag` 用 AND 拼接;同一 key 给两次不同 eq 写法(`--tag project=a --tag project=b`)合法,**返回空集**(系统不替你猜矛盾意图)。

**例子**

```bash
# 严格 ne,NULL 不算
memory.talk session list --tag status!=draft

# 没打过 project 标签的
memory.talk session list --tag !project

# status 落在这三个值任一
memory.talk session list --tag status=wip,review,blocked

# 组合:not draft AND 有 project
memory.talk session list --tag status!=draft --tag project
```

**当前限制**

- `K=V1,V2` 的 value 里**不支持** `,`(95% 的 tag value 是 slug 形,够用;真要带 `,` 再开 issue)
- 没有 `LIKE` / 前缀通配(`K~=prefix*` 之类),后续按需补
- 没有 `OR` 跨 key(`tag.A OR tag.B`)—— 想要 OR 用 IN 覆盖,真正跨字段 OR 当前 v3 全栈都没有(`search --where` 也只支持 AND)

#### 输出 — Markdown(默认)

跟 [`search`](search.md#markdown-默认) 同款 H3-per-result 块布局 —— 不用表格,因为:1) 单行 metadata 装不下完整 cwd / 多个 tag 又不丢失语义;2) CLI 渲染一致性更好,LLM 消费时识别成本低;3) 后续要加 `read <sid>` 之类的可点引用时,块结构更适合 inline 命令提示。

`````markdown
# session list

`filter: endpoint=claude-code · tag=project=billing` · 23 / 1247 results

---

### [SESSION] `sess-15f0a7fb-…190b0` · claude-code · 47 rounds

`tags: project=billing status=wip` · `cwd: ~/work/billing-svc` · 2026-05-24 09:12 (1 day ago)

---

### [SESSION] `sess-d68dd382-…0e7f` · codex · 12 rounds

`tags: project=infra` · `cwd: ~/work/infra` · 2026-05-24 08:30 (1 day ago)

---

### [SESSION] `sess-15f0a7fb-…b81c` · claude-code · 8 rounds

`cwd: ~/.memory.talk/explore` · 2026-05-23 14:21 (2 days ago)

---

_(showing 23 of 1247 — pass --limit higher to see more)_
`````

##### 约定

- 顶行 `# session list`,**不**带 query(没有 query 概念)。
- 第二行依次给出生效的过滤条件、返回数 / 总数 ——`23 / 1247` 表示"匹配 1247 条,本次返回 23 条"。没传任何过滤参数时第二行只有 `23 / 1247 results`,不出 `filter:` 段。
- 每条 session 一个 H3 块,块之间用 `---` 分隔 —— 跟 `search` 完全一致。
- H3 标题:`### [SESSION] \`<sid>\` · <source> · <round_count> rounds`
  - `[SESSION]` 字面前缀(类比 search 里的 `[CARD]` / `[SESSION]`)
  - sid 用反引号包住 —— 一眼能 copy-paste 给 `read`
  - 长 sid 不省略(`sess-<8hex>-<lastseg>` 已经天然短)
- 标题下空一行,接**一行 metadata**(中间用 ` · ` 分隔):
  - `tags: K=V K=V` —— 反引号包成 inline code;空 tags 时**整段不出**(不打 `tags: —` 之类占位符)
  - `cwd: <path>` —— 反引号包成 inline code;`$HOME` 会被压成 `~`;超 60 char 中间截断成 `<前 25>…<后 25>`
  - 绝对时间 + 相对时间 —— `YYYY-MM-DD HH:MM (X units ago)`,units 用 `min` / `hour` / `day` / `week`(跟 search 同款)
- 0 命中 → header 仍然出(`# session list\n\n\`filter: ...\` · 0 / 0 results`),不打 "no sessions found" 占位
- 总数 > 返回数时,末尾追一行 `_(showing N of TOTAL — pass --limit higher to see more)_` —— 等价于 search 的 strong-floor hint,提示用户结果被截
- **不**渲染 `metadata.cwd` 以外的 `metadata.*` 字段(平台原生 metadata 太杂,放进列表会噪声化;要看完整 metadata 走 `read <sid>`)

#### 输出 — JSON(`--json`)

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

### session tag

查 / 设 / 删 session 的 kv 标签。**单次调用可同时设多个 + 删多个**,服务端做 PATCH 语义合并。

```bash
# 查当前 tags(不传任何 K=V / -K)
memory.talk session tag <session_id>

# 设 / 改(K=V 多个,空格分隔)
memory.talk session tag <session_id> project=billing status=wip

# 删(-K 多个)
memory.talk session tag <session_id> -status -obsolete

# 设 + 删 混用
memory.talk session tag <session_id> project=billing -draft

# JSON 输出
memory.talk session tag <session_id> project=billing --json
```

#### 语法

| 形式 | 含义 |
|---|---|
| `K=V` | 设或覆盖 key `K` 为 value `V`。`V` 是字符串(整体当字符串存,**不做类型推断**) |
| `-K` | 删除 key `K`(已不存在则忽略,不报错) |
| 不传任何 K=V / -K | 只查,不改;输出当前 tags |

约束:
- key 必须匹配 `^[a-zA-Z][a-zA-Z0-9_.-]*$`(打头字母,后续可含 `_ . -`)。理由:CLI 解析需要避开 `-` 在第一个位置当成 unset 标记;`.` / `-` 留给后续命名空间约定(`ci.priority` 之类)。
- value 长度 ≤ 200 char。理由:tag 是"维度标签",不是"内容字段";超过 200 char 的语义应该塞 card 或 review,不该塞 tag。
- 单 session tag 数 ≤ 50。理由:超过这个量级通常是用错地方(应该用多张 card 而不是一堆 tag)。
- `K=V` 跟 `-K` 不能对同一 key 同时出现(`project=x -project` 报错)。

违反任一条 → 整次 PATCH 拒绝,exit 1,sessions table 不动。

#### 输出 — Markdown(默认)

设 / 删后:

````markdown
ok: `sess-15f0a7fb-…190b0` · tags = `project=billing status=wip`
````

只查时:

````markdown
# sess-15f0a7fb-…190b0 · tags

| key | value |
|---|---|
| project | billing |
| status  | wip |
````

session 没有任何 tag 时输出 `(no tags)`,exit 0。

#### 输出 — JSON(`--json`)

```json
{
  "session_id": "sess-15f0a7fb-...190b0",
  "tags": {"project": "billing", "status": "wip"}
}
```

无论是查还是改,返回都是**改动后的全量 tags**(方便消费方拿到最终状态,不用再回查)。

## 跟其他命令的边界

| 想做的事 | 用哪条 |
|---|---|
| 看一条 session 的原始对话 | `memory.talk read <session_id>` |
| 看一条 session 抽过几张 card / 几条 review | `memory.talk read <session_id>`(返回里带 referenced_by 摘要,后续会加) |
| 找还没被 card 引用过的 session | `memory.talk explore pending` |
| 找所有装在某个项目目录下的 session | `memory.talk session list --cwd ~/work/billing-svc` |
| 找所有打了 `status=wip` 标签的 session | `memory.talk session list --tag status=wip` |

`session list` 跟 `explore list` 的关系:`explore list` 是"在 explore namespace 下产出的 session"(`metadata.cwd startswith <explore.cwd>`),`session list` 是**全部** session 的通用入口 —— 想得到 explore list 的等价效果可以 `session list --cwd <explore.cwd>`,但 `explore list` 额外会带"产出 card / review 数量"列,所以两者并不完全互替,继续并存。

## 错误

| 情况 | 行为 |
|---|---|
| server 未运行 | `error: cannot reach server`,exit 1 |
| `--source` 是未注册 adapter | `error: unknown source 'xxx'`,exit 1(校验放 CLI 端,不下打 backend) |
| `--since` / `--until` 语法不合法 | `error: invalid duration '7days', use '7d' / '12h' / '2w' or ISO date`,exit 1 |
| `session tag` 的 sid 不存在 | `error: session 'sess-xxx' not found`,exit 1 |
| tag key 不合规 / value 太长 / 数量超限 | `error: tag key '<k>' invalid: ...`,exit 1,**不改任何 tag** |
| 同时 `K=V` 和 `-K` | `error: cannot both set and unset 'K' in the same call`,exit 1 |
