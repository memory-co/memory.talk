# seekbase — 数据库抽象层(v5 设计)

> **状态:设计中。** 定名 **seekbase**(seek = 既查〔结构化〕又寻〔语义〕的底座)。定位与 [searchbase](../v3/searchbase-extraction.md) 同一路数、**更进一步**:searchbase 把「向量检索」封成一个端口;seekbase 把**整个数据层**封成一个端口——一个**类 supabase 的通用 ORM**,底层 **DuckDB + LanceDB**,而且比 supabase 多一件事:**模糊(语义)查询是 ORM 里的一等算子**——查询链里写 `search(...)` 就自动语义检索。

相关:
- searchbase(它的前身与被吸收对象): [../v3/searchbase-extraction.md](../v3/searchbase-extraction.md) · [`memorytalk/searchbase/`](../../../memorytalk/searchbase/)
- v5 立意(memory system,seekbase 是它的数据层): [README.md](README.md)
- file-canonical 模式(与本层的关系见 §6): [../v3/file-canonical-pattern.md](../v3/file-canonical-pattern.md)

---

## 1. 问题:两条栈、手写 SQL、search 是外挂

当前数据层是**两条互不认识的栈**:

```
repository/*.py  ──手写 SQL──▶  SQLite(aiosqlite,结构化)
service/*.py     ──端口调用──▶  searchbase(LanceDB,向量)
```

- **每个名词一个 store、每个 store 手写 SQL**(`repository/` 下十几个文件,全是 `SELECT … WHERE …` 字符串)。加一列 = 改 DDL + 改 insert + 改 get + 改 list + 迁移,四五处手工同步。
- **结构化查询和语义查询是两个世界**:想要「**语义像这句话、且 kind=issue、且最近 30 天**」这种查询,得先 searchbase `search()` 拿 id,再回 SQLite `WHERE id IN (…)` 过滤,手工拼接、两边分页语义还对不上。
- **写入双写靠自觉**:每个 service 都要记得「插了行还要 upsert 向量」;删除同理(v4 `card delete` 的级联就是手工列清单)。漏一边 = 数据漂移。

这三个痛点是同一个病:**没有一个统一的数据端口**。searchbase 已经证明了「封端口」这条路(上层不认识向量、不算 embedding);seekbase 把同样的手法**推广到整个数据层**。

---

## 2. 它是什么:类 supabase 的 ORM,search 是一等算子

**一句话:supabase 式的通用查询体验,嵌在进程里,外加「`search()` 即模糊查询」。**

```python
db = await Seekbase.open(data_dir, schema=SCHEMA, embedder=embedder)

# ── 普通 ORM:supabase 风格的链式查询 ──────────────────────
rows = await (db.table("cards")
                .select("card_id", "issue", "created_at")
                .eq("kind", "issue")
                .gte("created_at", "2026-06-01")
                .order("created_at", desc=True)
                .limit(20))

await db.table("cards").insert({"card_id": "card_x", "issue": "…"})
await db.table("cards").update({"scope": "…"}).eq("card_id", "card_x")
await db.table("cards").delete().eq("card_id", "card_x")

# ── 超越 supabase:search() 就地模糊查询 ──────────────────
hits = await (db.table("cards")
                .search("为什么 pty 会让用户想到 tmux")   # ← 语义:自动 embed + 向量检索
                .eq("kind", "issue")                      # ← 结构化过滤,同一条链
                .gte("created_at", "2026-06-01")
                .limit(10))
# hits = 行 + score:结构化列全在,附 _score(相似度),按语义相关排序
```

要点:

- **通用 ORM(supabase 的那部分)**:`select / insert / upsert / update / delete` + `eq / neq / gt / gte / lt / lte / in_ / like / is_ / order / limit / offset / count`。链式构建、返回普通 dict 行。**上层(repository / service)不再手写 SQL。**
- **`search()`(supabase 没有的那部分)**:查询链里的一个**算子**,不是另一条 API。出现 `search(text)` 时,seekbase 自动:① 用注入的 embedder 把 `text` 变向量;② 到 LanceDB 检索;③ 与链上其余结构化谓词**组合**(过滤下推,见 §4);④ 返回带 `_score` 的行,按相关性排序。**调用方永远不见向量、不算 embedding**——这条纪律直接从 searchbase 继承。
- **schema 声明式**:表结构 + 哪些列可搜,声明一次,DDL / 迁移 / 双引擎同步全由 seekbase 管:

```python
SCHEMA = {
    "cards": {
        "columns": {"card_id": "str primary", "issue": "str",
                    "kind": "str", "created_at": "str"},
        "searchable": ["issue"],     # ← 声明这列可 search():写入自动 embed,search() 自动查
    },
    "rounds": {
        "columns": {"session_id": "str", "idx": "int", "text": "str"},
        "searchable": ["text"],
    },
}
```

**`searchable` 就是「search 函数自动模糊查询」的机制**:声明了它,`insert / update` 时该列文本自动 embed 进向量侧,`search()` 时自动查——写入方和查询方都不用碰第二条栈。没有 `searchable` 列的表就是纯 DuckDB 表,零向量开销。

---

## 3. 底层:DuckDB + LanceDB,一个端口两个引擎

```
                    Seekbase(端口:ORM + search 算子)
                    ┌───────────────┴───────────────┐
             结构化 / 分析                      向量 / 语义
              DuckDB(单文件)                LanceDB(已在用)
        行存取·过滤·聚合·join            embedding·ANN 检索
                    └──── id 对齐 + 写入同步(seekbase 管)────┘
```

- **DuckDB 承接 SQLite 的位置**(结构化引擎):同样嵌入式单文件、零运维,换来**列存 + 真分析能力**(聚合 / 窗口 / join 快得多——治理与巩固要在 corpus 上跑统计,这正是 memory system 的日常),且**原生读 Parquet / JSON**,和 LanceDB 的 Arrow 生态同宗。
- **LanceDB 原位保留**(向量引擎):searchbase 现在管的那摊(embed、ANN、集合)整体**下沉为 seekbase 的 search 引擎**;searchbase 作为独立端口**被吸收**——对外只剩 seekbase 一个端口(见 §7)。
- **双引擎同步是 seekbase 的内政**:`insert` 一行 → DuckDB 写行 + (有 `searchable` 列则)LanceDB upsert 向量;`delete` → 两边一起删;id 对齐、批量、重试都在端口后面。**上层从此没有「双写」这个概念。**

---

## 4. search() 与结构化谓词怎么组合

`search()` + `eq()/gte()/…` 混在一条链上时,执行策略(seekbase 内部,调用方无感):

1. **过滤下推(pre-filter)优先**:结构化谓词能翻成 LanceDB 的 filter 表达式的(等值 / 范围),直接下推到向量检索里——在**过滤后的子集**上做 ANN,保证「先过滤后取 top-k」的语义(不会出现「top-k 全被过滤掉、返回空」的 post-filter 病)。
2. **下推不了的谓词**(join / 复杂表达式):向量侧先取放大的候选(k × 放大系数),回 DuckDB 精过滤 + 补列,再截到 limit。
3. **没有 `search()` 的链**:纯 DuckDB,一次 SQL,不碰向量侧。
4. **排序语义**:带 `search()` 时默认按 `_score` 排;显式 `order()` 则按指定列(`_score` 仍附在行上)。

> 待定:`search()` 要不要同时融合关键词(BM25/FTS)做 hybrid(DuckDB 有 FTS 扩展,LanceDB 也有 hybrid 路线)。v1 先纯向量,接口上给 `search(text, mode="semantic")` 留出 `mode="hybrid"` 的位。

---

## 5. 为什么像 supabase、又不是 supabase

| | supabase | seekbase |
|---|---|---|
| 形态 | 云 BaaS(Postgres + PostgREST + 一堆服务) | **进程内嵌入库**(两个单文件引擎),零运维、本地优先 |
| 查询体验 | 通用 ORM / 链式构建器 | **一样**(照着这个体验做) |
| 模糊查询 | 无一等支持(pgvector 要自己拼) | **`search()` 一等算子**,自动 embed + 检索 + 组合过滤 |
| auth / realtime / 多租户 | 有 | **不做**(非目标;memory system 是单用户本地栈) |

学 supabase 的是**开发体验**(声明 schema、到处都是同一个链式查询);不学它的是**形态**(不做服务、不做云)。加上它没有的:**语义查询长在 ORM 里**。

---

## 6. 与 file-canonical 的关系:canonical 不变,派生层升级

[file-canonical 模式](../v3/file-canonical-pattern.md)**不动**:文件(YAML / JSON / JSONL)仍是权威,数据库仍是**派生索引、可重建**。变的只是派生层的实现:

```
v3/v4:  files(canonical) → SQLite(手写 store)+ LanceDB(searchbase 端口)
v5:     files(canonical) → seekbase(DuckDB + LanceDB,一个端口)
```

- 重建(reindex)= 读文件 → 灌 seekbase,一条路;
- 无 FOREIGN KEY、容忍悬空、表丢了能从文件重建——这些不变性照旧,由 seekbase 统一兑现;
- **seekbase 自己不读写 canonical 文件**(那是 Storage/repository 的事)——它只是那个「更好的派生索引」。

---

## 7. 与 searchbase 的关系:接棒并吸收

- searchbase 的**纪律全部继承**:业务无关(不认识 card / round)、调用方不见向量、embedder 注入、集合/文档抽象。
- searchbase 的**实现下沉**:`LocalSearchBackend` 那摊(LanceDB 管理、auto_split、超长截断、维护协程)成为 seekbase 向量侧的内部实现。
- searchbase 的**端口退役**:上层不再 import `SearchBackend`;`service/searchbase_schema.py` 那层「业务对象 → 集合」映射,被 §2 的声明式 SCHEMA(`searchable` 列)取代。
- **迁移路径**(粗):seekbase 先以新端口出现 → repository 逐个名词从「手写 SQL + searchbase 双调」搬到 seekbase → 搬完退役 aiosqlite 与 searchbase 端口。SQLite→DuckDB 的数据不用迁(派生层,从文件重建即可)。

---

## 8. 待定

- **ORM API 定形**:链式构建器的完整算子表;返回 dict 还是可选 pydantic 绑定;事务边界(DuckDB 内事务易,**跨引擎无原子性**——写顺序 + 对账兜底,策略要定)。
- **hybrid search**:`mode="hybrid"`(向量 + BM25)何时做、怎么融分(RRF?)。
- **DuckDB 并发模型**:单写者;daemon 内单连接串行化够不够,要不要写队列。
- **`searchable` 进阶**:多列 search、跨表 search(v4 unified search 那种 cards+insights+rounds 合并按相关排,在 seekbase 里怎么表达——`db.search("…", tables=[…])`?)。
- **迁移节奏**:v5 全新起 or 兼容期双跑;DuckDB 文件放哪、要不要和 LanceDB 同目录成一个「seekbase 实例目录」(像 searchbase 的 `name="v1"` 实例化路数)。

## 与其他 v5 文档的关系

- [README.md](README.md):seekbase 是 **memory system 的数据层**——问题图、session 索引、召回日志都落在它上面;memory system 的「能力」句子(结晶 / 治理 / 召回)最终都翻译成 seekbase 上的读写。
- 嵌入契约(待写):宿主(CC)经 CLI / API 驱动 memory system,不直接碰 seekbase;seekbase 永远是进程内的实现细节。
