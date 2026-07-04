# query — 共享 reality 的读面(v5 API)

自由 SQL 直通 **reality 库**(共享经验,[query-interface](../../works/v5/query-interface.md));schema 自描述就是「读 API 的文档」。**各 agent 的 mind 库**查询同语义,走 [`POST /v5/agents/{name}/query`](agent.md)。

## POST /v5/query

```json
{
  "sql":   "SELECT r.session_id, r.idx, r.text, s.score FROM semantic('rounds', '配 pty 提到 tmux') s JOIN rounds r ON r.session_id || ':' || r.idx = s.id ORDER BY s.score DESC LIMIT 10",
  "as_of": "2026-06-01T00:00:00Z"     // 可选:时光机(seekbase §7),回放该时刻的世界
}
```

响应:

```json
{
  "columns": ["session_id", "idx", "text", "score"],
  "rows": [["sess_9f2…", 37, "配 pty 时用户突然提了 tmux…", 0.87]],
  "row_count": 1,
  "truncated": false                   // 触到行数上限时 true
}
```

- **只读**:语句白名单(仅 `SELECT` / `WITH`);无 INSERT / UPDATE / DELETE / DDL → 400;
- **完全隔离**:本端点只见 reality;mind 的查询按实例走 [`/v5/agents/{name}/query`](agent.md)(互相不 ATTACH、不跨库 join)。mind → reality 的关联靠 `(type, ref, indexes)` **指针两步解析**(先在 agent mind 查 proofs,再按 type 来 reality / 文件取原文);
- **`semantic(collection, text)`**:语义检索表函数,返回 `(id, score)` 供 join(embedding 服务端算);
- **`as_of`**:整条查询回到该时刻(墓碑 / created_at 谓词自动改写;不带 = 当前世界);
- 防护:默认行数上限(如 1000,`truncated` 标记)、超时、`semantic()` 每语句次数限流 → 超限 400/408。

## GET /v5/schema

frame 的自描述——表 / 视图 / 列 + 注释(含 `semantic()` 的用法说明),机器可读:

```json
{ "library": "reality",
  "tables": { "sessions": { … }, "rounds": { "columns": { "idx": "轮号…", "text": "正文…" } }, "conversations": { … } },
  "views": { "v_sessions": "round_count/updated_at 现算…" },
  "functions": { "semantic": "semantic(collection, text) → (id, score)" } }
```

**AI 拿到这份就能自己写一切查询**——这就是 v5 不再堆读端点的原因。字段语义的人读版:[structure/v5](../../structure/v5/README.md)。
