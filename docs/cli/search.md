# search

更完善的搜索：同时搜 **Card** 和 **Session**，正文走 FTS + 向量混合检索，元数据通过独立 DSL 过滤。

```bash
memory-talk search "<FTS_QUERY>" [--where "<DSL>"] [--top-k N] [--format json|text]
```

| 参数 | 默认 | 说明 |
|------|------|------|
| `<FTS_QUERY>` 位置参数 | 必填（可为空串） | 正文搜索。Card 路走 FTS + 向量 hybrid（RRF 融合）；Session 路走 FTS（over rounds 全文） |
| `--where` / `-w` | 无 | 元数据过滤 DSL，两路共用 |
| `--top-k` | 10 | Card 和 Session 各自上限 |
| `--format` / `-f` | json | `json` / `text` |

空字符串 `<FTS_QUERY>` = "只按 `--where` 过滤"，两路各自按 `created_at desc` 返回。

## 位置参数：FTS 查询

交给 LanceDB native FTS（BM25）。支持：

- 自由词：`数据库 选型`（隐式 AND）
- `"精确短语"`：引号内作为 phrase 查询
- `-词`：排除

**不支持** `OR`、括号、嵌套。中文分词走 jieba。

同一个 query 同时喂给 Card 表和 Session 表两路索引。

## --where DSL

只作用于**元数据**。正文请用位置参数 FTS，不要尝试 `summary LIKE ...`。

### 可过滤字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | string | Card 路按 `cards.session_id`，Session 路按 `sessions.session_id` |
| `tag` | string（多值） | contains 语义，见下 |
| `created_at` | datetime | Card 路按 `cards.created_at`，Session 路按 `sessions.created_at` |
| `card_id` | string | **Card 专属**。出现此字段时 Session 路返回空 |

### 操作符

- 比较：`=` `!=` `>` `>=` `<` `<=`
- 模式：`LIKE` / `NOT LIKE`（`%` 任意、`_` 单字符）
- 集合：`IN (…)` / `NOT IN (…)`
- 组合：`AND`（显式或空格隐式）

### tag（contains 语义）

`tag` 来源于 `sessions.tags`（list），所有算子表达"列表里至少一个元素满足"：

```
tag = "decision"         # tags 包含 "decision"
tag LIKE "project:%"     # tags 里有任一以 "project:" 开头
tag IN ("a", "b")        # tags 里至少含 a 或 b
tag != "x"               # tags 不包含 "x"
```

### 时间字面量

```
created_at >= "2026-04-01"           # ISO 日期
created_at >= "2026-04-01T00:00:00"  # ISO 日期时间
created_at >= -7d                    # 相对：-7d / -30m / -24h / -4w
```

### 字符串字面量

双引号包裹：`"abc"`。裸 token 仅用于字段名、关键字、相对时间。

## 输出

```json
{
  "query": "LanceDB 选型",
  "where": "session_id = \"abc\" AND created_at >= -7d",
  "cards": {
    "results": [
      {
        "card_id": "01jz...",
        "summary": "决定用 LanceDB...",
        "session_id": "abc123",
        "ttl": 2592000,
        "score": 0.0324,
        "links": [
          {"link_id": "01jzq7rm", "id": "abc123", "type": "session", "comment": "...", "ttl": 100}
        ]
      }
    ],
    "count": 1
  },
  "sessions": {
    "results": [
      {
        "session_id": "abc123",
        "source": "claude-code",
        "tags": ["decision", "project:memory-talk"],
        "round_count": 42,
        "created_at": "2026-04-10T12:00:00",
        "score": 5.21
      }
    ],
    "count": 1
  }
}
```

- `cards.results[].score`：RRF 分数（越大越相关）
- `sessions.results[].score`：BM25 分数
- 两路分数不可直接比较
- Session 结果**不返回 rounds 原文**，请用 `memory-talk session read <SESSION_ID>` 读详情

## 示例

```bash
# 纯正文搜索
memory-talk search "LanceDB 选型"

# 正文 + 会话 + 时间范围
memory-talk search "数据库迁移 -mysql" \
  --where 'session_id = "abc" AND created_at >= -7d'

# 只按元数据筛，不要正文
memory-talk search "" \
  --where 'tag LIKE "project:%" AND created_at >= "2026-04-01"'

# 精确短语（等价于"正文精确子串"）
memory-talk search '"NFS 踩坑"' --top-k 20

# Card 专属字段：Session 路返回 count: 0
memory-talk search "迁移" --where 'card_id = "01jzq..."'
```

## 与 recall 的取舍

| | `recall` | `search` |
|---|---|---|
| 检索方式 | 纯向量相似度 | FTS 主 + 向量补（Card）/ FTS（Session） |
| 元数据过滤 | 不支持 | `--where` DSL |
| 返回类型 | Card | Card + Session |
| 适用场景 | 语义近似搜索（问答式） | 关键词精确匹配 / 条件筛选 / 找会话 |

一般优先 `search`。只有在明确只要"语义相似"而不关心关键词的场景下才用 `recall`。
