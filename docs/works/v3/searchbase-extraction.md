# searchbase 能力模块

把原本散在 `provider/` + `service/` 里的 embedding + LanceDB + index buffer，收敛成一个**通用搜索底座** `searchbase/`：对外只暴露一个 `SearchBackend` 端口，把 LanceDB / embedding 藏在端口背后，让未来的服务器版（换向量库 / 换 embedding）能整块替换、业务代码零改动。

关键约束：`searchbase` 是**通用**的——只认 `collection / document / id`，**不认识** `card` / `round` / `session` 这些 memory.talk 业务概念。业务映射留在 `service/`。

> **状态：已实施。** 整层迁移完成，旧 `LanceStore` / `IndexWriteBuffer` 已删除，485 测试全绿。
> **怎么用** 见模块内 [`../../../memorytalk/searchbase/README.md`](../../../memorytalk/searchbase/README.md)。本文讲**机制 + 设计决策 + 设计史**。

相关:
- 向量索引补齐 + EMFILE 恢复: [index-backfill.md](index-backfill.md)
- Search ranking(业务侧检索逻辑，保留在 service): [search-ranking.md](search-ranking.md)
- Session rounds 写入(写路径消费方之一): [session-rounds-write.md](session-rounds-write.md)
- Card 创建流程(写路径消费方之一): [card-creation-flow.md](card-creation-flow.md)

## 动机

目标：「后续 memory.talk 变成更高性能的服务器版本时，能方便地把 SQLite / LanceDB 换掉」。

让后端可插拔的**不是**按功能拆模块（cards/sync/search 纵切），而是给底层依赖定义**端口**、让 service 依赖端口不依赖实现。两个接缝：

- **SQL 侧（SQLite → Postgres）**：本就 80% 可插拔，`service/` 一句 SQL 都没有，全被 `repository/` 挡住。
- **向量侧（LanceDB → Qdrant/pgvector）**：原本漏成筛子——6 个 service 直接 import 具象 `LanceStore`、抓它的私有 `_segment`、调 `ensure_fts_index`/`.CARDS/.ROUNDS`。**这是本次解决的接缝。**

抽象边界按**能力**划不按技术划：embedding 和 LanceDB 永远一起出现、共享 dim、同一套生命周期 → 该是**一个**组件。服务器版很可能 embed + search 一次调用做完，根本拆不开。所以「搜索能力」才是替换单元。

## 最终结构

```
memorytalk/
  searchbase/
    __init__.py            对外导出：契约 + 值类型 + LocalSearchBackend
    _types.py              Doc/Query/Hit/IndexHealth(均 pydantic) + SearchBackend(Protocol) + errors
    local/                 local 实现
      backend.py           LocalSearchBackend：组合 embedder + 索引 + 切块/合并 + 维护协程
      index.py             CollectionIndex：通用集合存储（schema/CRUD/合并/EMFILE/压缩）
      _lance_helpers.py    纯 lance 查询/分词 helper（_run_hybrid / _segment / _is_emfile / _in_clause）
    README.md
  service/searchbase_schema.py   业务侧：collection schema 声明 + config→实例的 build_search_backend
  provider/                既不被 searchbase import；只剩 embedding.py(被业务用) + storage.py(文件镜像)
```

注意几个**和最初提案不同**的点：
- embedding **没搬进 searchbase**。`searchbase` 不 import `provider`，而是构造时**收一个 embedder 对象**（鸭子类型 `embed`/`embed_one`）。`provider/embedding.py` 留在原地被业务用。
- 没有 `buffer.py`。`IndexWriteBuffer` 被**删除**——写入改成立即落盘（见下）。
- `index.py` 是**新写的通用 `CollectionIndex`**，不是 `lancedb.py` 原样搬。纯 helper 抽到 `_lance_helpers.py`。
- 类型不是 dataclass 而是 **pydantic**（与 `schemas/` 一致），放在 `_types.py`（避免和 `__init__` 循环 import）。
- `server/` **还没建**（deferred）。

## 契约 `SearchBackend`（`_types.py`，只认 collection / Doc / id）

```python
class SearchBackend(Protocol):
    @property
    def ready(self) -> bool: ...                 # False → api 返回 503
    async def close(self) -> None: ...           # 停后台维护协程
    async def health(self) -> IndexHealth: ...   # fd/压缩/EMFILE 可观测性
    async def upsert(self, collection, docs: list[Doc]) -> None: ...
    async def delete(self, collection, ids) -> None: ...
    async def delete_where(self, collection, match: dict) -> None: ...
    async def search(self, collection, query: Query) -> list[Hit]: ...
    async def count(self, collection, match=None) -> int: ...
```

**被藏起来的 lance-isms**：`_segment`(分块)、`ensure_fts_index`、表名常量、`optimize`/compaction、EMFILE 恢复、dim、embedder。调用方传**文本**、不碰向量——这是可插拔的关键。

**为什么没有 `index_cards`/`search_cards`**：`card`/`round`/`session` 是业务概念，通用底座不该认识；它们退化成调用方传入的 `collection` 字符串。

## 构造：命名实例 + 固定声明 schema

构造是**异步类工厂**（开库 + 起维护协程都要 await），收**明确值、不读 Config**：

```python
backend = await LocalSearchBackend.create(
    name="v1", data_dir=config.vectors_dir, dim=384, embedder=...,
    collections={"cards": {"fields": {}},
                 "rounds": {"fields": {...}, "auto_split": True}},
    max_text_length=2000,
)
```

- **实例 = 命名目录 + 固定 schema**。`name` → local 落在 `<data_dir>/<name>/`。
- schema 是**声明的、不是首行推断的**（避免「首行字段是 null → 列被错判成字符串 → 数值过滤崩」这类坑，对抗审查实测复现过）。
- config→参数的映射唯一落在 `service/searchbase_schema.build_search_backend(config)`——**唯一**读 `config.settings` 来拼 searchbase 的地方。它也是将来按 config 选 local/server 的接缝。

## 关键行为

**写入立即落盘（无 buffer）。** `upsert` 整批 embed + 一次 `table.add` = 每 session 一个 fragment（远好于旧的每 10 行一个）。因此 `bump_indexed_count` 紧跟 `upsert` 之后即可、计数准确——不再需要 buffer 的延迟 flush + flush 回调那套。

**`max_text_length` 超长策略（按 collection 走）。**
- `auto_split=False`（默认，如 cards）：超长 → 抛 `SearchError`，**不静默截断**。（card 超长被拒也安全：card 不进 backfill、不会死循环，卡照建只是不进索引。）
- `auto_split=True`（如 rounds）：超长 → searchbase **内部切多块**，每块一行、共享隐藏 `_base_id`/`_chunk`，**对外完全不可见**：
  - `search` 按 `_base_id` 把块**合并成一条** Hit（取最高分）
  - `count` 只数每 doc 的 `_chunk = 0` → 返回**逻辑 doc 数**
  - `delete`/`delete_where` 按 `_base_id` 删光一个 doc 的所有块

  → 业务代码一行不用改，眼里永远只有逻辑 doc。rounds 必须切（单轮可能很长，否则超长 round 会让 backfill 死循环）。

**碎片合并 / fd / EMFILE 全在内部、自动。** 实例自带后台维护协程（`close()` 停）：**启动压一次 + 每 `compact_interval_seconds`（默认 1800s）周期压一次**，把 append-only 碎片合并掉；search 万一仍遇 EMFILE 再「压缩+重连+重试一次」兜底。`health().detail` 给数字（`compactions` / `last_compact_*` / `emfile_recoveries` / …），供 `/v3/sync/status`。

## 业务映射（在 `service/`）

```python
# service/searchbase_schema.py —— 业务的领域词汇 + schema 声明
CARDS, ROUNDS = "cards", "rounds"
SCHEMAS = {CARDS: {"fields": {}},
           ROUNDS: {"fields": {"session_id": "str", "idx": "int", "role": "str"}, "auto_split": True}}
def round_doc_id(sid, idx): return f"{sid}:{idx}"
async def build_search_backend(config): ...   # config → LocalSearchBackend.create(...)

# service/cards.py / sessions.py —— 业务负责「业务对象 → 通用 Doc」
await self.search.upsert(CARDS, [Doc(id=card_id, text=cap_text(insight), fields={})])
await self.search.upsert(ROUNDS, [Doc(id=round_doc_id(sid, idx), text=cap_text(text),
                                      fields={"session_id": sid, "idx": idx, "role": role})])
await self.search.delete_where(ROUNDS, {"session_id": sid})
```

## 迁移结果（消费方怎么变）

| 对象 | 变化 |
|---|---|
| `provider/lancedb.py` | **删除**（纯 helper 进 `searchbase/local/_lance_helpers.py`） |
| `service/index_buffer.py` | **删除**（写入立即落盘） |
| `api/__init__.py` | `LanceStore.create`+`get_embedder`+`IndexWriteBuffer` 一坨 → `await build_search_backend(config)`；lifespan 关停调 `searchbase.close()` |
| `service/cards.py` | `embed_one + add_card` → `upsert(CARDS, …)`；`delete_cards` → `delete` |
| `service/sessions.py`(Ingest) | `embed + _segment + buffer` → `upsert(ROUNDS, …)`；`bump_indexed_count` 紧跟其后（按 round 数） |
| `service/search.py` / `recall.py` | `(vectors, embedder)` → 依赖 `SearchBackend`；`search_cards/rounds` → `search(collection, Query)`；qvec 由 backend 内部算 |
| `service/backfill.py` | 只剩重嵌；compaction 交给 searchbase；`delete_session_rounds`→`delete_where`、`add_rounds`→`upsert` |
| `api/sync.py` | index 健康字段改读 `searchbase.health().detail` |

## 和旧实现的行为差异（都是有意简化）

1. **rounds 索引变「整 session 全有或全无」**（原来按 chunk 部分成功）。失败→session 降级→backfill 重试，仍收敛，只是失败粒度变粗。
2. **周期性压缩从 backfill 搬进 searchbase 的维护协程**（启动 + 每 30 分钟），不再是 backfill 的职责；语义不变。
3. **索引目录变 `<vectors_dir>/v1/`**——老用户原扁平索引成了「上个版本」，由 backfill 重建。

## 设计史（为什么是现在这样）

- **schema 怎么定**：首行推断 → 太脆（null/类型/缺字段都会坑，审查实测复现）→ 改成**构造时声明、不可变**。
- **超长怎么办**：静默截断（藏数据丢失，否决）→ 业务切分（会散落到业务的 count/去重）→ **searchbase 按 collection 切 + 读取合并**（对业务全隐藏，最干净）。`auto_split` 跟着 schema 走：rounds 开、cards 不开。
- **谁记 indexed_count**：曾想用 `searchbase.count()` 替代 SQLite 计数；最终发现立即落盘后，业务 `bump_indexed_count(round 数)` 即准，`count()` 不必承重（仅作通用查询）。
- **buffer / flush**：曾设计 FlushListener 回调解耦 session 计数 → 立即落盘后整套不需要，删除。
- **searchbase 是否读 Config**：曾 `make_search_backend(config)` 偷读 settings → 改成收明确值、config 映射抽到 `build_search_backend`，searchbase 既不 import Config 也不 import provider。
- **值类型 dataclass→pydantic**：与 `schemas/` 一致。
- **类不可见 + 三层工厂**：删 `make_search_backend`，把类型挪 `_types.py` 解循环 import，包顶层直接暴露 `LocalSearchBackend`。

## 还没做（deferred）

- `searchbase/server/` 骨架（远端命名索引，蓝绿换名同一套抽象）。
- **setup 自动感知 embedding 最大输入长度**写进 settings（local 读 `model.max_seq_length`；HTTP 查表 + 保守兜底）——现在 `MAX_TEXT_LENGTH=2000` 是写死常量，见 `searchbase_schema.py` 的 `TODO(setup-sense)`。
- **升级流程**作为独立模块：改 schema = 开新实例 + 业务回填（含 cards 重嵌，当前 backfill 只重嵌 rounds），老实例服务到切换。
