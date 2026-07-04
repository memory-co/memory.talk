# query — 唯一的读面(v5 API)

自由 SQL 直通两库([query-interface](../../works/v5/query-interface.md));schema 自描述就是「读 API 的文档」。

## POST /v5/query

```json
{
  "sql":   "SELECT c.card_id, c.issue, s.score FROM semantic('cards', '为什么 pty 会想到 tmux') s JOIN cards c ON c.card_id = s.id WHERE c.position_count = 0 ORDER BY s.score DESC LIMIT 10",
  "as_of": "2026-06-01T00:00:00Z"     // 可选:时光机(seekbase §7),回放该时刻的世界
}
```

响应:

```json
{
  "columns": ["card_id", "issue", "score"],
  "rows": [["card_01j…", "为什么 pty 会让用户想到 tmux", 0.87]],
  "row_count": 1,
  "truncated": false                   // 触到行数上限时 true
}
```

- **只读**:语句白名单(仅 `SELECT` / `WITH`);无 INSERT / UPDATE / DELETE / DDL → 400;
- **两库同见**:mind + reality ATTACH 在同一条只读连接,跨库 join 直接写表名;
- **`semantic(collection, text)`**:语义检索表函数,返回 `(id, score)` 供 join(embedding 服务端算);
- **`as_of`**:整条查询回到该时刻(墓碑 / created_at 谓词自动改写;不带 = 当前世界);
- 防护:默认行数上限(如 1000,`truncated` 标记)、超时、`semantic()` 每语句次数限流 → 超限 400/408。

## GET /v5/schema

frame 的自描述——表 / 视图 / 列 + 注释(含 `semantic()` 的用法说明),机器可读:

```json
{ "libraries": { "mind": { "tables": { "cards": { "columns": { "card_id": "card_<ULID>", "issue": "问题文本…" } }, … },
                            "views": { "v_positions": "计数+credence 现算…", … } },
                 "reality": { … } },
  "functions": { "semantic": "semantic(collection, text) → (id, score)" } }
```

**AI 拿到这份就能自己写一切查询**——这就是 v5 不再堆读端点的原因。字段语义的人读版:[structure/v5](../../structure/v5/README.md)。
