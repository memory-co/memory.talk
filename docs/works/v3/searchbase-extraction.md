# searchbase 能力模块抽取（提案）

把当前散在 `provider/` + `service/` 里的 embedding + LanceDB + index buffer，收敛成一个**通用搜索底座** `searchbase/`：对外只暴露一个 `SearchBackend` 契约，把 LanceDB / embedding 这类实现藏在契约背后，让未来的服务器版（换向量库 / 换 embedding）能整块替换，而业务代码零改动。

关键约束：`searchbase` 是**通用**的——它只认 `collection / document / id`，**不认识** `card` / `round` / `session` 这些 memory.talk 业务概念。业务概念的映射留在 `service/`。

> **状态：设计提案，未实施。** 代码现状仍是 `provider/lancedb.py`、`provider/embedding.py`、`service/index_buffer.py` 分散 + service 直接 import 具象类。本文是动手前的方案。

相关:
- 向量索引补齐 + EMFILE 恢复: [index-backfill.md](index-backfill.md)
- Search ranking(业务侧检索逻辑，保留在 service): [search-ranking.md](search-ranking.md)
- Session rounds 写入(写路径消费方之一): [session-rounds-write.md](session-rounds-write.md)
- Card 创建流程(写路径消费方之一): [card-creation-flow.md](card-creation-flow.md)

## 动机

目标是「后续 memory.talk 变成更高性能的服务器版本时，能方便地把 SQLite / LanceDB 换掉」。

让后端可插拔的**不是**按功能拆模块（cards/sync/search 纵切），而是给底层依赖定义**端口（接口）**，让 service 依赖接口、不依赖实现。当前两个接缝的健康度：

- **SQL 侧（SQLite → Postgres）**：已经 80% 可插拔。`service/` 里一句 SQL 都没有，全被 `repository/` 挡住了。
- **向量侧（LanceDB → Qdrant/pgvector）**：漏成筛子。6 个 service 文件直接 import 具象的 `LanceStore`，还伸手抓它的私有 `_segment`，并调用 `ensure_fts_index`、`.CARDS/.ROUNDS` 这些 lance 专有概念。**这是本次要解决的接缝。**

抽象边界按**能力**划，不按技术划：embedding 和 LanceDB 永远一起出现、共享同一个维度(dim)、同一套生命周期 —— 它们该是**一个**组件。服务器版很可能 embed + search 是一次调用做完，根本拆不开。所以「搜索能力」才是替换单元。

## 目录结构（和 `service/` 平级）

```
memorytalk/
  service/                  ← 业务（改动：依赖从 vectors/embedder 变成 SearchBackend）
  searchbase/               ← 新增·通用搜索底座
    __init__.py             ← 对外 interface 的全部（契约 + 类型 + errors + factory）
    local/                  ← 当前实现（embedding + lancedb）
      __init__.py
      backend.py            ← LocalSearchBackend：实现契约，组合下面三个 + glue
      embedding.py          ← 从 provider/embedding.py 搬来
      index.py              ← 从 provider/lancedb.py 搬来（_segment 等也进来）
      buffer.py             ← 从 service/index_buffer.py 搬来
    server/                 ← 未来的服务器版（现在只搭骨架）
      __init__.py
      backend.py            ← ServerSearchBackend：NotImplementedError 占位
```

**测试沿用现有集中结构**，不迁进模块。在 `tests/` 下新增 `tests/searchbase/`：

```
tests/
  searchbase/               ← 新增，和 tests/service、tests/provider 平级
    __init__.py
    test_local_backend.py
    test_buffer.py          ← 从 tests/service/test_index_buffer.py 搬来
    test_chunking.py        ← 从 tests/provider/test_embedding_chunking.py 搬来
    test_emfile.py          ← 从 tests/provider/test_emfile_recovery.py 搬来
```

搬完之后，旧 `provider/` 只剩 `storage.py`（文件镜像）—— 那是另一种能力，**本次不动**（将来可独立成 `storage/`）。

## `searchbase/__init__.py` 对外暴露什么（仅此而已）

```python
# 契约
class SearchBackend(Protocol): ...
# 通用值类型（不知道自己是 card 还是 round；调用方传「文本」，完全不碰向量）
@dataclass class Doc:    id: str; text: str; fields: dict      # fields 既用于过滤，也随命中返回
@dataclass class Query:  text: str; top_k: int = 10; filters: dict | None = None
@dataclass class Hit:    id: str; score: float; fields: dict
@dataclass class IndexHealth: ...                              # 给 sync status 用
# errors
class SearchError(Exception): ...
class SearchUnavailable(SearchError): ...        # lance 打不开 → 端点返回 503
class EmbedderInvalid(SearchError): ...          # boot 时校验失败
# factory（看 config 选 local/server，唯一「知道用的是谁」的地方）
def make_search_backend(config) -> SearchBackend: ...
```

`local/`、`server/` 里的东西**一律不 export**。service 能 import 到的只有上面这些。

## 契约 `SearchBackend` 的方法（通用：只认 collection / Doc / id）

```python
class SearchBackend(Protocol):
    # 生命周期
    async def start(self) -> None: ...
    async def stop(self) -> None: ...            # 把 buffer 排空再关
    @property
    def ready(self) -> bool: ...                 # False → api 返回 503
    async def compact(self) -> None: ...         # 启动时 compaction（旧 optimize）
    async def flush(self) -> int: ...            # backfill 重建索引前强制排空
    async def health(self) -> IndexHealth: ...   # sync status 展示用

    # 写（embed、分块、buffer 全藏在内部）
    async def upsert(self, collection: str, docs: list[Doc]) -> None: ...
    async def delete(self, collection: str, ids: list[str]) -> None: ...
    async def delete_where(self, collection: str, match: dict) -> None: ...

    # 读（ensure_fts_index 在内部惰性执行）
    async def search(self, collection: str, query: Query) -> list[Hit]: ...
```

**被藏起来的 lance-isms**：`_segment`(分块)、`ensure_fts_index`、`CARDS/ROUNDS` 表名常量、`optimize`、buffer 的存在、dim、embedder。调用方传文本、不碰向量 —— 这是可插拔的关键。

**为什么没有 `index_cards` / `search_cards`**：`card` / `round` / `session` 是 memory.talk 业务概念，通用底座不该认识。它们退化成调用方传进来的 `collection` 字符串（`"cards"` / `"rounds"`）。

## 业务映射留在 service（业务才知道 card 长什么样）

```python
# service/cards.py —— 业务负责「card → 通用 Doc」+ 知道集合叫 "cards"
await self.search.upsert("cards", [Doc(id=card_id, text=req.insight, fields={...})])

# service/sessions.py —— 业务负责「round → 通用 Doc」
docs = [Doc(id=f"{sid}:{r.index}", text=r.text, fields={"session_id": sid, ...}) for r in rounds]
await self.search.upsert("rounds", docs)

# 删某 session 的全部 round = 按条件删（不是按 id）
await self.search.delete_where("rounds", {"session_id": sid})
```

集合名常量 `CARDS = "cards"` / `ROUNDS = "rounds"` 放在 **service 侧**（业务的领域词汇），不进 `searchbase`。

## 搬迁映射（谁怎么变）

| 对象 | 操作 |
|---|---|
| `provider/embedding.py` | → `searchbase/local/embedding.py`（搬） |
| `provider/lancedb.py` | → `searchbase/local/index.py`（搬，`_segment` 一起） |
| `service/index_buffer.py` | → `searchbase/local/buffer.py`（搬） |
| glue（`_segment` + lance_rows 拼装 + optimize） | → 集中进 `searchbase/local/backend.py` |
| `service/search.py`（业务） | **保留**。`(vectors, embedder)` → 依赖 `SearchBackend`。collection 映射 + merge / tag 过滤 / 整形仍是业务 |
| `service/recall.py` | 同上 |
| `service/cards.py` | `embed_one + add_card` → `search.upsert("cards", [Doc(...)])` |
| `service/sessions.py`(Ingest) | `embed + _segment + buffer.add_rounds` → `search.upsert("rounds", docs)` |
| `service/backfill.py` | 「哪些 session 要重建」判断作为业务保留。`optimize`→`compact`、`add_rounds`→`upsert`、`delete_session_rounds`→`delete_where`、`flush`→`flush` |
| `api/__init__.py`（组装根） | 把 `LanceStore.create` + `get_embedder` + `IndexWriteBuffer` 这一坨换成**一行** `make_search_backend(config)`。lifespan 里调 `start/stop/compact`。给各 service 注入 backend |

**业务 / 能力的分界线**：「collection 映射、query 解析、tag 过滤、card 和 session 命中合并、结果整形」留在 `service/` 是业务。`searchbase/` 只管「embed、建索引、向量检索」，不认识任何业务概念。

## 组装根 before/after

```python
# before（api/__init__.py，约 40 行在伺候 lance/embedder/buffer）
vectors = await LanceStore.create(config.vectors_dir, dim=...)
embedder = get_embedder(config); await validate_embedder(config)
app.state.index_buffer = IndexWriteBuffer(vectors=..., db=..., ...); app.state.index_buffer.start()
# 把 vectors, embedder, index_buffer 分发给各 service

# after
search = make_search_backend(config)   # 唯一知道用哪个实现的地方
await search.start()
app.state.search = search
# 各 service 只拿到 search。compact / stop 也都收敛到 search 上
```

## 待确认的设计点

1. ~~模块名~~ → **已定：`searchbase`**（通用搜索底座，与业务侧 `service/search.py` 区分开）。
2. **lance 不可用时**：backend 永远返回、用 `ready=False` 让 api 返回 503（废掉 `if vectors is None` 的散落判断）。
3. **`server/` 本次只搭骨架**（`NotImplementedError`），先把架子立起来。
4. ~~测试搬迁~~ → **已定：测试沿用现有集中结构**，不进模块。在 `tests/` 下新增 `tests/searchbase/`（和 `tests/service`、`tests/provider` 平级），共用 rootdir 的 `tests/conftest.py`。

## 实施顺序（每步保持测试绿）

1. `searchbase/__init__.py` 定义契约 + 通用类型 + errors（不写实现，先写测试）
2. 把 embedding / lancedb / buffer **只搬不改**进 `local/`（改 import，测试绿）
3. 实现 `LocalSearchBackend`，跑通契约测试（glue + collection→lance 表映射集中到这里）
4. 消费方逐个改成依赖 backend（顺序：search → recall → cards → sessions → backfill），每改一个保绿
5. 组装根换成 `make_search_backend`
6. 加 `server/` 骨架
7. 清扫旧 `_segment`/直接 import 残留（grep 查漏）
