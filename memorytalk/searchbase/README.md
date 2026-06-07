# searchbase

通用、与业务无关的搜索底座。把 embedding + 向量库（当前 LanceDB）封在一个端口背后，让上层只跟「集合 / 文档 / id」打交道，**不认识 card / round / session 这些业务概念**。

业务对象 → 集合文档的映射不在这里，在 [`../service/searchbase_schema.py`](../service/searchbase_schema.py)。

---

## 一分钟上手

```python
from memorytalk.searchbase import LocalSearchBackend, Doc, Query

# 构造 = 异步类工厂（开库 + 起后台维护协程都要 await）
backend = await LocalSearchBackend.create(
    name="v1",                       # 实例名 → local 落在 <data_dir>/v1/
    data_dir=config.vectors_dir,     # 普通 Path，searchbase 不读 Config
    dim=384,                         # 向量维度
    embedder=my_embedder,            # 任何带 embed()/embed_one() 的对象
    collections={
        "cards":  {"fields": {}},
        "rounds": {"fields": {"session_id": "str", "idx": "int"},
                   "auto_split": True},
    },
    max_text_length=2000,            # 超长写入的处理上限（见下）
)

# 写：调用方只给文本，向量由 backend 内部算
await backend.upsert("cards", [Doc(id="card_1", text="用 RRF 做混合检索", fields={})])

# 读：query 也只给文本，embedding 在内部完成
hits = await backend.search("cards", Query(text="混合检索", top_k=5))
for h in hits:
    print(h.id, h.score, h.fields)

# 计数 / 删除
await backend.count("rounds", {"session_id": "sess_x"})   # 该 session 已索引几条
await backend.delete("cards", ["card_1"])
await backend.delete_where("rounds", {"session_id": "sess_x"})

await backend.close()                # 关停后台协程
```

> 真实接线在组装根：`api/__init__.py` 调 `service/searchbase_schema.build_search_backend(config)`，那是**唯一**读 `config.settings` 来拼这些参数的地方；searchbase 自己不碰 Config。

---

## 契约：`SearchBackend`（[`_types.py`](_types.py)）

| 方法 | 作用 |
|---|---|
| `await create(...)` | 类工厂，返回已在运行的实例（无单独 `start`） |
| `await close()` | 停后台维护协程 |
| `ready` (property) | 底层是否可用；`False` → 上层应回 503 |
| `await health()` → `IndexHealth` | fd/压缩/EMFILE 可观测性，给 `/v3/sync/status` |
| `await upsert(collection, docs)` | 写入/按 id 替换（embedding、分块在内部） |
| `await delete(collection, ids)` | 按逻辑 doc id 删 |
| `await delete_where(collection, match)` | 按字段等值删 |
| `await search(collection, query)` → `list[Hit]` | 向量 + FTS 混合检索（RRF） |
| `await count(collection, match=None)` → `int` | 匹配字段的**逻辑** doc 数 |

值类型（pydantic，[`_types.py`](_types.py)）：
- `Doc(id, text, fields)` — 待写入的文档；调用方永不碰向量
- `Query(text, top_k=10, filters=None)`
- `Hit(id, score, fields)`
- `IndexHealth(ready, detail)`

---

## collection schema 格式

构造时一次性声明，**之后不可变**（要改 schema 见「实例 = 版本」）：

```python
{
  "<collection>": {
      "fields": {"<字段名>": "str" | "int" | "float" | "bool", ...},
      "auto_split": <bool, 默认 False>,
  },
}
```

- `fields`：除 `id` / `text` / `vector` 之外要存的列（既用于 `match` 过滤，也随 `Hit.fields` 返回）。
- schema 是**声明的、不是从首行推断的**——避免「首行某字段是 null → 列被错判成字符串」这类坑。

---

## 几个关键行为

**`max_text_length` —— 超长怎么办**
- `auto_split=False`（默认）：超长 → 抛 `SearchError`，**不静默截断**。调用方自己截/拆。
- `auto_split=True`：超长 → searchbase **内部切成多块**，每块一行、共享隐藏的 `_base_id`。切块对外**完全不可见**：
  - `search` 把同一逻辑 doc 的块**合并成一条** `Hit`（取最高分）
  - `count` 只数每个 doc 的 chunk 0 → 返回**逻辑 doc 数**，不是块数
  - `delete` / `delete_where` 按 `_base_id` 删光一个 doc 的所有块

  > 谁开 auto_split 跟着 schema 走：rounds 开（单轮可能很长，切块好过失败→否则 backfill 会死循环）；cards 不开（insight 短，超长直接拒绝、卡照建只是不进索引）。

**实例 = 版本（蓝绿升级）**
一个实例 = 一个命名目录 + 一套固定 schema。**改 schema = 开一个新名字的新实例**，由业务把数据回填进去；老实例继续服务，切过去再删。searchbase 不含任何 rebuild / 迁移 / backfill 逻辑。

**fd / 压缩 / EMFILE —— 全在内部**
启动时后台跑一次 compaction（碎片合并），搜索遇到 EMFILE 自动「压缩 + 重连 + 重试一次」。这些细节不对外暴露，`health().detail` 只给可观测数字。

---

## 纪律

- `searchbase/` 里**不出现任何业务词**（card/round/session）——只有 collection / Doc / id。
- searchbase **不读 Config、不依赖 provider**；它收明确的值（`data_dir` / `dim` / `embedder` / `collections` / `max_text_length`）。
- 想换后端（LanceDB → Qdrant/pgvector）：在 `local/` 旁加一个实现、让 `build_search_backend` 按 config 选——业务代码一行不改。

## 目录

```
searchbase/
  __init__.py        对外导出：契约 + 值类型 + LocalSearchBackend
  _types.py          Doc / Query / Hit / IndexHealth / SearchBackend(Protocol) / errors
  local/             local 实现（embedding + LanceDB）
    backend.py       LocalSearchBackend：组合 embedder + 索引 + 切块/合并 + 维护协程
    index.py         CollectionIndex：通用集合存储（schema、CRUD、合并、EMFILE 恢复、压缩）
    _lance_helpers.py  纯 LanceDB 查询/分词 helper（_run_hybrid / _segment / …）
  server/            未来的服务器版（占位）
```

> 设计来由与决策史见 [`../../docs/works/v3/searchbase-extraction.md`](../../docs/works/v3/searchbase-extraction.md)。
