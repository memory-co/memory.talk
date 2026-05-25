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
    [--tag K=V ...] [--tag K ...] \
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
| `--tag K=V` | `key=value` | tag 必须有这个 key 且 value 严格相等;多个 `--tag` AND |
| `--tag K` | `key` | 只要存在这个 key 即命中(value 任意) |
| `--since` / `-d` | 持续时长或 ISO 日期 | session `created_at >= 起点`;`7d` / `12h` / `2w` / `2026-05-01` |
| `--until` | 同上 | session `created_at <= 终点` |
| `--limit` | 整数,默认 `20` | 最多返回多少条;按 `created_at` 倒序后截 |

`--since` / `--until` duration 语法:`<int><unit>`,unit ∈ `{h, d, w}`(小时 / 天 / 周)。`-d` 是 `--since` 的短选项(高频用法,跟 `git log --since` 风格一致)。

#### 输出 — Markdown(默认)

````markdown
# session list · 23 / 1247

| created_at | session_id | source | cwd | rounds | tags |
|---|---|---|---|---|---|
| 2026-05-24 09:12 | `sess-15f0a7fb-…190b0` | claude-code | `~/work/billing-svc` | 47 | `project=billing status=wip` |
| 2026-05-24 08:30 | `sess-d68dd382-…0e7f`  | codex       | `~/work/infra`        | 12 | `project=infra` |
| 2026-05-23 14:21 | `sess-15f0a7fb-…b81c`  | claude-code | `~/.memory.talk/explore` | 8  | — |
…
````

标题里 `N / Total`:`N` 是本次返回(受 `--limit` 截断),`Total` 是匹配条件的总数(给用户判断要不要扩 limit 的提示)。`cwd` 截到 50 char,超出用 `…`。`tags` 列空字典渲染为 `—`。

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
