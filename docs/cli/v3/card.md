# card

Talk-Card 的写入 + 维护入口。0.8.x 起拆成**二级命令**,跟 [session](session.md) 同款思路:

```
memory.talk card
├── create '<json>' [--json]                          # 写一张新 card(immutable, append-only)
├── list [filters...] [--limit N] [--json]            # 按结构性条件列已有 card
└── tag <card_id> [K=V ...] [-K ...] [--json]        # 查 / 加 / 删 card 上的 kv 标签
```

读对话内容统一走 [`memory.talk read <card_id>`](read.md);"按相关度找 card" 走 [`memory.talk search`](search.md)。

> **0.8.x 破坏性改名**:`memory.talk card '<json>'` 不再是 valid 形式 —— 必须改写成 `memory.talk card create '<json>'`。`card` 当前是 group 命令,不带子命令调用直接 print help。理由:同时挂"写一张"和"列 / 标签维护"两类语义在一个一级命令上,职责混淆 + LLM tool-use 描述很难写清。

## 设计原则

1. **写入 vs 维护分开**。`create` 是认知动作(沉淀一个新洞见),`list` / `tag` 是组织动作(给已有 card 归类 / 找出特定子集)。两类操作的关注点不同 —— 拆子命令让职责面干净。
2. **card 的内容仍 append-only,但 tag 是元数据,不是内容**。`insight` / `rounds` / `source_cards` 一旦创建仍**不可改**(论坛动力学的基础),`tag` 是 user-side metadata,跟 stats / `read_count` 同等地位 —— 改 tag 不破坏 [README §七](README.md#七设计原则) 的 append-only 不变性。
3. **list 只接结构性 / metadata 过滤,不接 stats**。"按 review_up 找 / 找 shadow card / 找争议 card" 是论坛动力学的查询,继续走 [`search "" -w '...'`](search.md#dsl)。`card list` 的位置是:**按物理属性(tag / 创建时间)找子集做批量维护**,不跟 search 的动力学查询重叠。
4. **tag 是 key-value 字典,跟 session tag 同结构**。跨对象一致的 tag 模型(string→string,同款约束)让用户记忆负担最小;后续要做"按 tag 跨 card+session 联合查"也水到渠成。

---

## card create

创建一张新 Talk-Card。

```bash
memory.talk card create '<json>' [--json]
```

输入 JSON 结构、字段规则、indexes 语法、副作用 **跟 0.7.x 的 `memory.talk card '<json>'` 完全一致** —— 这里只列字段名,语义详见下方各小节。

```json
{
  "insight": "选定 LanceDB 做向量存储",
  "rounds": [
    {"session_id": "sess-15f0a7fb-…190b0", "indexes": "11-15"},
    {"session_id": "sess-d68dd382-…0e7f",  "indexes": "3,7,12"}
  ],
  "source_cards": [
    {"card_id": "card_01jzaaaa", "relation": "supersedes"},
    {"card_id": "card_01jzbbbb", "relation": "derives_from"}
  ],
  "tags": {"project": "billing", "status": "draft"}
}
```

### 字段

- `insight`(必填):一句话认知洞见,也是 embedding 锚点。
- `rounds`:引用列表,每项 `{session_id, indexes}`。`session_id` 必须是 `sess-…` / `sess_…` 形态。写入者不传原始对话内容,服务端按 `session.rounds[].index` 展开成 `{role, text}` 存入 card。可为空列表 —— 基于多个 card 合成、无原始 session 来源的新 card 属于这种情况。
- `source_cards`(可选):card 之间的关联,**创建时确定,不可修改**。每项 `{card_id, relation}`:
  - `card_id`:被引用 card 必须存在,前缀必须是 `card_<…>`。
  - `relation`:
    - `derives_from`(默认):本卡基于该 card 蒸馏 / 综述而来(高阶 card 引用低阶 card 的典型形态)。
    - `supersedes`:本卡**反驳并替代**该 card(fork 语义)。老 card 不被删,继续在论坛里存在,后续是否真被取代由动力学(review 分布 + 沉浮排序)说了算 —— 没有"立即把老 card 打成 dormant"这种硬切换。
    - 后续可能扩展 `cites` / `merges` 等;未识别 `relation` 报错。

  空列表 / 不传等价。同一 `card_id` 允许在 `source_cards` 里以不同 `relation` 多次出现(罕见但不禁止)。

  > **lineage 自然成 DAG**:card 一旦创建不可修改 + `source_cards` 只能引用**创建时已存在**的 card,物理时序就保证 lineage 图是有向无环图,服务端不做环检测。
- `tags`(可选):创建时直接带 tag,等价于 create 完再跑一次 `card tag <cid> K=V ...`。约束跟 [card tag](#card-tag) 一致(key 正则 / value 长度 / 总数上限);任意一条不合规 → 整条 create 拒绝。
- `card_id`(可选):不提供则自动生成 `card_<ULID>`。传入时必须是 `card_<…>` 形态。

### indexes 语法

两种形式:

| 形式 | 示例 | 含义 |
|---|---|---|
| 区间 | `"11-15"` | 闭区间 `[11, 15]`,展开为 `11,12,13,14,15` |
| 列表 | `"3,7,12"` | 离散的 index 列表 |

约束(不满足即拒绝整次写入):

- **必须严格单调递增** —— `"15-11"` / `"12,7,3"` 报 `indexes must be monotonically increasing`。
- **越界或引用不存在的 index**(包括大于 session `round_count` 或 session 本身不存在)报 `index N out of range for session <session_id>`。
- 同一个 `session_id` 允许在 `rounds` 列表里多次出现(用于跳过中间段);不同 item 之间无顺序约束。

### 输出 — Markdown(默认)

````markdown
ok: created `card_01jz8k2m`
````

错误(到 stderr,exit 1):

````markdown
**error:** index 99 out of range for session `sess-15f0a7fb-…190b0`
````

### 输出 — JSON(`--json`)

```json
{"status": "ok", "card_id": "card_01jz8k2m"}
```

```json
{"error": "index 99 out of range for session sess-15f0a7fb-...190b0"}
```

返回的 `card_id` 就是**以后所有地方用的读取凭据** —— 直接喂给 `read` 即可。

### 副作用

- 校验并展开 `rounds` 引用:失败则整条 card 不落库。
- 展开后的每条 round 存为 `{role, text, session_id, index}` —— 直接把引用信息内联到 round 里。`session_id` 与 `index` 不进向量索引。
- 校验 `source_cards` 里每个 `card_id` 存在、`relation` 合法;失败则整条 card 不落库。
- 校验 `tags`(如有);失败则整条 card 不落库。
- 自动计算 insight 的 embedding 并写入向量库。
- 在 log 里追加:本 card 的 `created` 事件、每个被引用 session 的 `card_extracted` 事件、每个 `source_cards` 项的 `card_linked` 事件(被引 card 的视角)。
- 本卡 stats 初始化为零(`review_up` / `review_down` / `review_neutral` / `review_count` / `read_count` / `recall_count` 全 0)。后续随 review / read / recall 自动累加,详见 [read](read.md) 的 stats 字段。

---

## card list

按结构性条件列已有 card,**只回元数据 + insight 摘要**(不展开 rounds[])。跟 [`session list`](session.md#session-list) 同款 H3-per-result 块布局。

```bash
memory.talk card list \
    [--tag K=V ...] [--tag K ...] \
    [--since <duration|date>] [-d <duration|date>] \
    [--until <duration|date>] \
    [--limit N] [--json]
```

### 过滤参数

| 参数 | 取值 | 说明 |
|---|---|---|
| `--tag K=V` | `key=value` | tag 必须有这个 key 且 value 严格相等;多个 `--tag` AND |
| `--tag K` | `key` | 只要存在这个 key 即命中(value 任意) |
| `--since` / `-d` | 持续时长或 ISO 日期 | card `created_at >= 起点`;`7d` / `12h` / `2w` / `2026-05-01` |
| `--until` | 同上 | card `created_at <= 终点` |
| `--limit` | 整数,默认 `20`,上限 `200` | 最多返回多少条;按 `created_at` 倒序后截 |

> 不接 stats 过滤(`review_up >= N`、`read_count` 等)—— 这类查询走 [`search "" -w 'DSL'`](search.md#dsl),不在 `card list` 重复实现。
>
> 不接 lineage 过滤(`--cites <sid>` / `--derives-from <cid>` / `--supersedes <cid>`)—— 后续 PR 补,本轮先把结构性 + tag 拉通。

### 输出 — Markdown(默认)

`````markdown
# card list

`filter: tag=status=draft` · 12 / 47 results

---

### [CARD] `card_01jz8k2m` · `↑7 ↓3 · reviews 12 · reads 42 · recalls 18`

选定 **LanceDB** 做向量存储,主要因为零依赖嵌入式架构

`tags: project=billing status=draft` · 2026-05-24 09:12 (1 day ago)

---

### [CARD] `card_01jzp3nq` · `↑2 ↓0 · reviews 2 · reads 5 · recalls 1`

LanceDB 落地后的踩坑清单

`tags: project=billing status=draft` · 2026-05-25 14:21 (just now)

---

_(showing 12 of 47 — pass --limit higher to see more)_
`````

#### 约定

- 顶行 `# card list`;第二行 `\`filter: ...\` · N / TOTAL results`(filter 段在无过滤时省略,只保留 `N / TOTAL results`)
- 每条 card 一个 H3 块,块间 `---` 分隔 —— 跟 `search` 的 `[CARD]` 块布局**完全一致**:
  - 标题:`### [CARD] \`<card_id>\` · \`<stats inline>\``。stats 用反引号包成 inline code,`↑N ↓N` 是 review_up / review_down,`reviews` 是总数(含中立),`reads` / `recalls` 是路过类信号
  - 标题下空一行,**整段 `insight` 直接展开** 作为普通段落(不抽 snippet)
  - 再空一行,一行 metadata:`\`tags: K=V K=V\` · <绝对时间> (<相对时间>)`,空 tags 时整段不出
- 总数 > 返回数时末尾追 `_(showing N of TOTAL — pass --limit higher to see more)_`,跟 `session list` 同款句式
- 0 命中 → header 仍然出(`# card list\n\n0 / 0 results`),不打 "no cards found" 占位

### 输出 — JSON(`--json`)

```json
{
  "total": 47,
  "returned": 12,
  "cards": [
    {
      "card_id": "card_01jz8k2m",
      "insight": "选定 LanceDB 做向量存储,主要因为零依赖嵌入式架构",
      "created_at": "2026-05-24T09:12:03Z",
      "tags": {"project": "billing", "status": "draft"},
      "stats": {
        "review_up": 7,
        "review_down": 3,
        "review_neutral": 2,
        "review_count": 12,
        "read_count": 42,
        "recall_count": 18
      }
    }
  ]
}
```

`stats` 字段语义跟 [`search`](search.md#type--card-专属字段) 同款,详见 [`../../structure/v3/talk-card.md#Stats`](../../structure/v3/talk-card.md#stats)。

---

## card tag

查 / 设 / 删 card 的 kv 标签。跟 [`session tag`](session.md#session-tag) **完全同款语义** —— PATCH 合并 + 不传任何参数 = 查询。

```bash
# 查
memory.talk card tag <card_id>

# 设 / 改
memory.talk card tag <card_id> project=billing status=draft

# 删
memory.talk card tag <card_id> -status -draft

# 混用
memory.talk card tag <card_id> status=verified -draft

# JSON
memory.talk card tag <card_id> project=billing --json
```

### 语法

| 形式 | 含义 |
|---|---|
| `K=V` | 设或覆盖 key `K` 为 value `V`。`V` 是字符串(整体当字符串存,**不做类型推断**) |
| `-K` | 删除 key `K`(已不存在则忽略,不报错) |
| 不传任何 K=V / -K | 只查,不改;输出当前 tags |

### 约束(跟 session 同步)

- key 必须匹配 `^[a-zA-Z][a-zA-Z0-9_.-]*$`
- value 长度 ≤ 200 char
- 单 card tag 数 ≤ 50
- `K=V` 跟 `-K` 不能对同一 key 同时出现

任一违反 → 整次 PATCH 拒绝,exit 1,cards 表不动。

### 跟 append-only 不变性的关系

card 的**内容**(`insight` / `rounds` / `source_cards`)一旦 create 不可改 —— 这是论坛动力学的物理基础(老 card 不被改写,只能被新 card supersede)。`tags` 是 **user-side metadata**(类比 stats 是 system-side metadata),跟内容字段完全解耦:

- 改 tag **不会** 改 insight / rounds / source_cards
- 改 tag **不会** 触发任何 `superseded` 之类的语义(纯组织标签)
- 改 tag **不会** 进 vector index(不影响 search)
- 改 tag **不会** 触发 review / stats 任何字段变化

所以 `card tag` 不破坏 [README §七](README.md#七设计原则) 的"Card append-only"原则 —— 那条原则约束的是**内容**,不是元数据。

### 输出 — Markdown(默认)

设 / 删后:

````markdown
ok: `card_01jz8k2m` · tags = `project=billing status=verified`
````

只查时:

````markdown
# card_01jz8k2m · tags

| key | value |
|---|---|
| project | billing |
| status  | verified |
````

无 tag 时输出 `(no tags)`,exit 0。

### 输出 — JSON(`--json`)

```json
{
  "card_id": "card_01jz8k2m",
  "tags": {"project": "billing", "status": "verified"}
}
```

无论查还是改,返回都是**改动后的全量 tags**(方便消费方拿到最终状态,不用回查)。

---

## 跟其他命令的边界

| 想做的事 | 用哪条 |
|---|---|
| 写一张新 card | `card create '<json>'` |
| 看一张 card 的完整内容 / 论坛位置 | `read <card_id>` |
| 按相关度找 card(query / 沉浮公式) | `search <query> -w 'type = "card"'` |
| 按 stats 找 card(shadow / 争议 / 被反驳) | `search "" -w 'review_count = 0 AND read_count > 10'` 等 DSL |
| 按 tag / 时间找 card | `card list --tag status=draft --since 7d` |
| 给 card 加 / 删 tag | `card tag <cid> K=V -K` |
| 给某张 card 写 review(回帖) | `review '<json>'` |

`card list` 跟 `search` 的分工:**`card list` 走结构性属性(tag / 时间),`search` 走相关度 + 论坛动力学**。两者覆盖不同的查询场景,不互相替代。

## 错误

| 情况 | 行为 |
|---|---|
| server 未运行 | `error: cannot reach server`,exit 1 |
| `card` 不带任何子命令 | 打印 help,exit 0 |
| `card create` 任一字段不合规 | `error: <details>`,exit 1,什么也不入库 |
| `card list` 的 `--since` / `--until` 语法不合法 | `error: invalid duration '7days', use '7d' / '12h' / '2w' or ISO date`,exit 1 |
| `card tag` 的 cid 不存在 | `error: card 'card_xxx' not found`,exit 1 |
| `card tag` 任一 tag 不合规 | `error: tag key '<k>' invalid: ...`,exit 1,**不改任何 tag** |
| `card tag` 同时 `K=V` 和 `-K` | `error: cannot both set and unset 'K' in the same call`,exit 1 |
