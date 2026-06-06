# Search DSL

`memory.talk search ... -w '<DSL>'` 的字段表达式语法。

相关:
- CLI: [`../../cli/v3/search.md`](../../cli/v3/search.md)
- 代码: `memorytalk/util/dsl.py`

## 支持的字段

| 字段类型 | 字段名 | 仅适用于 |
|---|---|---|
| 类型切片 | `type`(`"card"` / `"session"`) | 两边都行 |
| 元数据 | `session_id`、`card_id`、`source`、`created_at` | 各自的桶(card 没有 `source`,session 没有 `card_id`) |
| Card 论坛信号 | `review_up`、`review_down`、`review_neutral`、`review_count`、`read_count`、`recall_count` | **只对 cards 应用** |

## 运算符

`=`、`!=`、`<`、`>`、`<=`、`>=`、`LIKE`、`IN`、`NOT IN`、`AND`。

## 字段应用域规则

DSL 里某个字段如果**不属于**当前候选的类型,这个候选会被**整条过滤掉**:

- `where: 'review_count = 0'` → 只保留 cards(sessions 没有此字段)
- `where: 'source = "claude-code"'` → 只保留 sessions(cards 没有此字段)
- `where: 'created_at > "2026-04-01"'` → cards 和 sessions 都按各自的 `created_at` 过滤

想要"只看 card"或"只看 session"用 `type`:

```bash
memory.talk search "LanceDB" -w 'type = "card"'      # 只 cards
memory.talk search "LanceDB" -w 'type = "session"'   # 只 sessions
```

## 示例

```bash
# 元数据过滤
memory.talk search "LanceDB" -w 'source = "claude-code"'
memory.talk search "" -w 'created_at > "2026-04-01"'
memory.talk search "bug" -w 'session_id = "sess_abc123"'

# shadow knowledge:被路过得多但没人真讨论过的 card
memory.talk search "" -w 'read_count > 10 AND review_count = 0'

# 高争议:赞踩都不少
memory.talk search "" -w 'review_up >= 3 AND review_down >= 3'

# 被反驳更多的 card(可能要 fork)
memory.talk search "" -w 'review_down > review_up'

# 类型切片
memory.talk search "LanceDB" -w 'type = "card"'
memory.talk search "LanceDB" -w 'type = "session"'
```

## 错误

DSL 解析失败:

````markdown
**error:** DSL parse error: unknown field 'foo'
````

`--json` 模式下:

```json
{"error": "DSL parse error: unknown field 'foo'"}
```

退出码 1。

## 跟 tag filter 的差别

`-w` 是 DSL(SQL-ish 表达式),作用于内置字段。
`--tag K=V` 是 tag filter(键值匹配),作用于用户自定义的 `tags` map。

两者可以同时用,AND 关系:

```bash
memory.talk search "LanceDB" -w 'review_up > 3' --tag project=billing
```

tag filter 的语法细节见 `util/tag_filter.py`。
