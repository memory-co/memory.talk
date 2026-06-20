# insight

**v3 那套卡改名而来**(一句 `insight` + rounds + 论坛 stats)。v4 把 `card` 这个名字腾给问答卡之后,老数据整体改名 `insight`:**数据保留、只读 + 可搜,不再是抽卡主路径**。新抽卡只写 v4 卡(`card` / `card position`)。

```
memory.talk insight
├── search --query '<q>' [--where '<DSL>'] [--limit N] [--json]   # 搜老洞见卡
└── view --id <insight_id> [--json]                              # 读一条老洞见卡
```

走 v3 改名后的端点 `/v3/insights`(见 [`../../works/v4/card.md`](../../works/v4/card.md#9-与-v3--insight-的共存与迁移))。数据结构沿用 v3 talk-card(`insight` / `rounds` / `stats` / `reviews`),只是前缀 `card_` → `insight_`。

> **只读**:`insight` 没有 create / review 子命令——老数据冻结。要继续往问题图里沉淀,用 [`card`](card.md)(create / position / review / link)。老洞见可逐条**投影**进 v4 图(一条 insight → 一张卡 + 一个 Position),投影策略见 works §9 步骤三。

## insight search

跟 v3 论坛检索同款(撞 `insight` 文本 + 沉浮排序),只是范围限定在 insight 集合。hybrid FTS + 向量 + stats DSL 过滤,按融合分降序返回。

```bash
memory.talk insight search --query '向量库选型' [--where '<DSL>'] [--limit N] [--json]
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--query` | — | 检索文本。可为空(配合 `--where` 做纯 stats 过滤) |
| `--where` | 无 | stats / 元数据过滤 DSL(下表字段) |
| `--limit` | 10 | 结果数上限 |
| `--json` | 关 | 输出 JSON 而非 Markdown |

### DSL 字段(沿用 v3,老数据仍带这套 stats)

老 insight 卡保留 v3 那套 6 计数器,DSL 直接按这些字段过滤:

| 字段 | 含义 |
|---|---|
| `review_up` | `score=+1` review 数 |
| `review_down` | `score=-1` review 数 |
| `review_neutral` | `score=0` review 数 |
| `review_count` | review 总数(= up + down + neutral) |
| `read_count` | 本卡被 read 命中的次数 |
| `recall_count` | 本卡被 recall 返回过的次数 |
| `created_at` | ISO 8601 创建时间 |

运算符:`=` / `!=` / `>` / `>=` / `<` / `<=`,以 `AND` / `OR` 组合。例:

```bash
memory.talk insight search --query 'LanceDB' --where 'read_count > 10 AND review_count = 0'
memory.talk insight search --query '' --where 'review_up >= 3'
```

`score` 是 LanceDB RRF 融合分,典型 `0.01–0.03`,**只看排名不看绝对相似度**。

## insight view

```bash
memory.talk insight view --id insight_01jz8k2m [--json]
```

输出沿用 v3 卡的读取形态:`insight` 文本 + 展开的 rounds + stats + reviews。前缀 `insight_`(原 `card_` 改名)。

### 输出 — Markdown(默认)

````markdown
# INSIGHT `insight_01jz8k2m`

**Insight:** 选定 LanceDB 做向量存储

**Stats:** ↑1 ↓1 · reviews 3 · reads 8 · recalls 4

**From:**

- `supersedes` → `insight_01jzaaaa`
- `derives_from` → `insight_01jzbbbb`

## reviews (3)

- **+1** `sess_abc123` #20-25 — 再次确认 LanceDB 选型,生产跑了 3 个月稳定
- **-1** `sess_def456` #5,8 — 原以为 mmap NFS 没事,生产撞了 inode lock 的坑
- **0** `sess_xyz789` #11 — 又讨论到了,没改变结论

## rounds (2)

**[`sess_abc123`#11 human]**

ChromaDB vs LanceDB?

---

**[`sess_abc123`#12 assistant]**

推荐 **LanceDB**:零依赖、嵌入式
````

约定:
- 顺序固定:头部元数据(`Insight` / `Stats` / `From`)→ `## reviews`(无 review 时省略)→ `## rounds`。
- `**Stats:**` inline 单行:`↑<review_up> ↓<review_down> · reviews <review_count> · reads <read_count> · recalls <recall_count>`。
- `**From:**` 展示 `source_cards`,每条 `\`<relation>\` → \`<insight_id>\``;无则整段省略。`relation` 取值 `derives_from` / `supersedes`。
- `## reviews` 按 `created_at` 倒序,每条 `**±N** \`<sess_id>\` #<indexes> — <comment>`;`score=0` 显示 `**0**`;无 review 整段省略。
- `## rounds` 放最后,每个 round 用 `---` 分隔;round 内第一行 `**[\`<sess_id>\`#<idx> <role>]**`,空一行后是原样 round 正文。

### 输出 — JSON(`--json`)

```json
{
  "type": "insight",
  "read_at": "2026-04-20T14:32:05Z",
  "insight": {
    "insight_id": "insight_01jz8k2m",
    "insight": "选定 LanceDB 做向量存储",
    "source_cards": [
      {"insight_id": "insight_01jzaaaa", "relation": "supersedes"}
    ],
    "rounds": [
      {"role": "human", "text": "ChromaDB vs LanceDB?", "session_id": "sess_abc123", "index": 11},
      {"role": "assistant", "text": "推荐 LanceDB 零依赖", "session_id": "sess_abc123", "index": 12}
    ],
    "reviews": [
      {"review_id": "review_01jzr5kq", "session_id": "sess_abc123", "indexes": "20-25", "score": 1, "comment": "再次确认 LanceDB 选型", "created_at": "2026-05-01T09:14:22Z"}
    ],
    "stats": {
      "review_up": 1, "review_down": 1, "review_neutral": 1,
      "review_count": 3, "read_count": 8, "recall_count": 4
    },
    "created_at": "2026-04-10T14:30:00Z"
  }
}
```

字段语义(immutable payload + runtime stats + reviews 倒序快照)沿用 v3 talk-card 模型,只是前缀 `card_` → `insight_`、不再可写。

## 错误

| 情况 | 行为 |
|---|---|
| `insight_id` 前缀错 / 不存在 | `error: insight '<id>' not found`,exit 1 |
| 在 `insight` 上调写操作 | `error: insight is read-only; use 'card' / 'review'`,exit 1 |
