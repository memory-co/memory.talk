# query — 共享 reality 的读面(v5 API)

自由 SQL 直通 **reality 库**(共享经验,[query-interface](../../works/v5/query-interface.md));schema 自描述就是「读 API 的文档」。**各 agent 的 mind 库**查询同语义,走 [`POST /v5/agents/{name}/query`](agent.md)。

## POST /v5/query

```json
{
  "sql":    "SELECT session_id, idx, text, _score FROM rounds WHERE search(text, '配 pty 提到 tmux') ORDER BY _score DESC LIMIT 10",
  "ds_end": "20260601"                 // 可选:时光机(seekbase §7),回到那天结束时的世界
}                                       // 另有 ds_start:创建日下界(时间窗)
```

响应:

```json
{
  "columns": ["session_id", "idx", "text", "_score"],
  "rows": [["sess_9f2…", 37, "配 pty 时用户突然提了 tmux…", 0.87]],
  "row_count": 1,
  "truncated": false                   // 触到行数上限时 true
}
```

- **只读**:语句白名单(仅 `SELECT` / `WITH`);无 INSERT / UPDATE / DELETE / DDL → 400;
- **完全隔离**:本端点只见 reality;mind 的查询按实例走 [`/v5/agents/{name}/query`](agent.md)(互相不 ATTACH、不跨库 join)。mind → reality 的关联靠 `(type, ref, indexes)` **指针两步解析**(先在 agent mind 查 proofs,再按 type 来 reality / 文件取原文);
- **`search(列, '文本')`**:语义检索 SQL 函数(列须声明 `searchable`,每列一个向量索引);命中分数 = `_score_<列>` 列(单个 search 附别名 `_score`);embedding 服务端算;
- **`ds_end` / `ds_start`**(`YYYYMMDD`,天粒度):只给 `ds_end` = 时光机(事件重放到那天,seekbase §7);`ds_start` = 创建日下界;都不给 = 当前世界;
- 防护:默认行数上限(如 1000,`truncated` 标记)、超时、`search()` 每语句次数限流 → 超限 400/408。

## GET /v5/schema

frame 的自描述——表 / 视图 / 列 + 注释(含 `search()` 的用法说明),机器可读:

```json
{ "library": "reality",
  "tables": { "sessions": { … }, "rounds": { "columns": { "idx": "轮号…", "text": "正文…" } }, "conversations": { … } },
  "views": { "v_sessions": "round_count/updated_at 现算…" },
  "functions": { "search": "search(列, 文本) — searchable 列的语义命中;分数列 _score_<列>" } }
```

**AI 拿到这份就能自己写一切查询**——这就是 v5 不再堆读端点的原因。字段语义的人读版:[structure/v5](../../structure/v5/README.md)。
