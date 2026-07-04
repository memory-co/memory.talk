# seekbase — 数据库抽象层(v5 设计)

> **状态:设计中。** 定名 **seekbase**(seek = 既查〔结构化〕又寻〔语义〕的底座)。定位与 [searchbase](../v3/searchbase-extraction.md) 同一路数、**更进一步**:searchbase 把「向量检索」封成一个端口;seekbase 把**整个数据层**封成一个端口——一个**类 supabase 的通用 ORM**,底层 **DuckDB + LanceDB**,而且比 supabase 多一件事:**模糊(语义)查询是 ORM 里的一等算子**——查询链里写 `search(...)` 就自动语义检索。

相关:
- searchbase(它的前身与被吸收对象): [../v3/searchbase-extraction.md](../v3/searchbase-extraction.md) · [`memorytalk/searchbase/`](../../../memorytalk/searchbase/)
- v5 立意(memory system,seekbase 是它的数据层): [README.md](README.md)
- file-canonical 模式(与本层的关系见 §10): [../v3/file-canonical-pattern.md](../v3/file-canonical-pattern.md)

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
await db.table("cards").delete().eq("card_id", "card_x")   # ← 仅打墓碑(deleted_at),永不物理删
# 没有 update:「改」= 追加新行 / 追加事件 + 旧行墓碑(见下「焊死的不变性」)

# ── 超越 supabase:search() 就地模糊查询 ──────────────────
hits = await (db.table("cards")
                .search("为什么 pty 会让用户想到 tmux")   # ← 语义:自动 embed + 向量检索
                .eq("kind", "issue")                      # ← 结构化过滤,同一条链
                .gte("created_at", "2026-06-01")
                .limit(10))
# hits = 行 + score:结构化列全在,附 _score(相似度),按语义相关排序
```

要点:

- **通用 ORM(supabase 的那部分,砍掉修改类)**:`select / insert / delete` + `eq / neq / gt / gte / lt / lte / in_ / like / is_ / order / limit / offset / count`。链式构建、返回普通 dict 行。**上层(repository / service)不再手写 SQL。**
- **焊死的不变性:只能增、不能改、不能物理删。** 端口**没有 `update` / `upsert`**;`delete()` 的唯一语义是**打墓碑**(`deleted_at`,引擎代管的元数据列);物理删除在端口上不存在(仅 `vacuum` 这个显式丢历史的管理动作,§7)。「改」在 seekbase 的世界里 = **追加**:新行取代旧行(旧行墓碑)、会变的值落成事件表 + 视图现算。这条**不是调用方纪律,是引擎强制**——收益在 §7:时光机因此对**所有列**严谨,不存在「被后来 update 污染的历史」。
- **`search()`(supabase 没有的那部分)**:查询链里的一个**算子**,不是另一条 API。出现 `search(text)` 时,seekbase 自动:① 用注入的 embedder 把 `text` 变向量;② 到 LanceDB 检索;③ 与链上其余结构化谓词**组合**(过滤下推,见 §4);④ 返回带 `_score` 的行,按相关性排序。**调用方永远不见向量、不算 embedding**——这条纪律直接从 searchbase 继承。
- **schema 声明式**:表结构 + 哪些列可搜,声明一次,DDL / 迁移 / 双引擎同步全由 seekbase 管:

```python
SCHEMA = {
    "cards": {
        "columns": {"card_id": "str primary", "issue": "str",
                    "kind": "str", "created_at": "str"},
        "searchable": ["issue"],     # ← 声明这列可 search():写入自动 embed,search() 自动查
        "files": "cards/{card_id}.json",         # ← 声明本地 JSON 镜像:写入自动落文件(可 grep,§6)
    },
    "rounds": {
        "columns": {"session_id": "str", "idx": "int", "text": "str"},
        "searchable": ["text"],
        "files": {"path": "sessions/{session_id}/rounds.jsonl", "mode": "jsonl"},  # 追加型大表用 JSONL
    },
}
```

**`searchable` 就是「search 函数自动模糊查询」的机制**:声明了它,`insert` 时该列文本自动 embed 进向量侧,`search()` 时自动查——写入方和查询方都不用碰第二条栈。没有 `searchable` 列的表就是纯 DuckDB 表,零向量开销。

---

## 3. 底层:一个端口 = 两个引擎 + 一份文件镜像

```
                    Seekbase(端口:ORM + search 算子)
                    ┌───────────────┴───────────────┐
             结构化 / 分析                      向量 / 语义
              DuckDB(单文件)                LanceDB(已在用)
        行存取·过滤·聚合·join            embedding·ANN 检索
                    └──── id 对齐 + 写入同步(seekbase 管)────┘
```

- **DuckDB 承接 SQLite 的位置**(结构化引擎):同样嵌入式单文件、零运维,换来**列存 + 真分析能力**(聚合 / 窗口 / join 快得多——治理与巩固要在 corpus 上跑统计,这正是 memory system 的日常),且**原生读 Parquet / JSON**,和 LanceDB 的 Arrow 生态同宗。
- **LanceDB 原位保留**(向量引擎):searchbase 现在管的那摊(embed、ANN、集合)整体**下沉为 seekbase 的 search 引擎**;searchbase 作为独立端口**被吸收**——对外只剩 seekbase 一个端口(见 §11)。
- **双引擎同步是 seekbase 的内政**:`insert` 一行 → DuckDB 写行 + (有 `searchable` 列则)LanceDB upsert 向量;`delete` → 两边同步打墓碑(向量 doc 的 `deleted_at` 字段,正常检索 pre-filter 掉);id 对齐、批量、重试都在端口后面。**上层从此没有「双写」这个概念。**

---

## 4. search() 与结构化谓词怎么组合

`search()` + `eq()/gte()/…` 混在一条链上时,执行策略(seekbase 内部,调用方无感):

1. **过滤下推(pre-filter)优先**:结构化谓词能翻成 LanceDB 的 filter 表达式的(等值 / 范围),直接下推到向量检索里——在**过滤后的子集**上做 ANN,保证「先过滤后取 top-k」的语义(不会出现「top-k 全被过滤掉、返回空」的 post-filter 病)。
2. **下推不了的谓词**(join / 复杂表达式):向量侧先取放大的候选(k × 放大系数),回 DuckDB 精过滤 + 补列,再截到 limit。
3. **没有 `search()` 的链**:纯 DuckDB,一次 SQL,不碰向量侧。
4. **排序语义**:带 `search()` 时默认按 `_score` 排;显式 `order()` 则按指定列(`_score` 仍附在行上)。

> 待定:`search()` 要不要同时融合关键词(BM25/FTS)做 hybrid(DuckDB 有 FTS 扩展,LanceDB 也有 hybrid 路线)。v1 先纯向量,接口上给 `search(text, mode="semantic")` 留出 `mode="hybrid"` 的位。

---

## 5. 写入原子性:内建消息队列(outbox)

**跨引擎没有事务**(DuckDB 的事务包不住 LanceDB 的写),这是 §3 双引擎的原罪。seekbase 用**内建消息队列**解决——经典 **transactional outbox**,而且有个巧处:**队列本身就放在 DuckDB 里**,于是「业务写 + 入队」天然是**同一个 DuckDB 事务**,原子性不出引擎就拿到了。

```
insert / delete=墓碑(带 searchable 列)
        │
        ▼ 一个 DuckDB 事务(原子)
┌────────────────────────────────┐
│ ① 写业务行(cards …)           │
│ ② 追加 _outbox 一行(向量作业)  │   _outbox(seq, table, op, id, text, state)
└────────────────────────────────┘
        │ commit 后
        ▼ 后台 consumer(单个,进程内)
   逐条取 pending → embed → LanceDB upsert/delete → 标 done
   失败 → 退避重试;崩溃 → 重启后从 pending 续跑(replay)
```

- **写路径永不碰 LanceDB**:调用方 `insert()` 返回时,DuckDB 行 + outbox 作业**要么都在、要么都不在**。向量侧由 consumer 异步兑现。
- **at-least-once + 幂等 = 收敛**:consumer 可能重放(标 done 前崩溃),但向量写是**按 id upsert / delete**——天然幂等,重放无害。**不需要恰好一次。**
- **一致性语义:向量侧最终一致。** `search()` 可能滞后于刚写入的行(通常毫秒级)。要读己之写的场合(如 mark 写路径「先撞库再建卡」)给 `await db.flush()`——排干 outbox 再继续。结构化查询(不带 `search()`)永远强一致。
- **顺序**:outbox 按 `seq` 单 consumer 串行消费,同一 id 的 upsert/delete 不会乱序。
- **崩溃恢复 = 重放,不需对账**:任何时刻崩,pending 作业都还在 DuckDB 里(和业务行同一事务落的),重启接着跑。彻底丢了也不怕——派生层照旧可从 canonical 文件整体重建(§10)。
- **delete 同路**:级联删(如 `card delete`)在一个 DuckDB 事务里删行 + 入队向量删除作业,两边终归一致。

> 这个队列是 **seekbase 的内政**:上层看不见 outbox、consumer、重试——只看见「写完就返回、search 最终能搜到、要强读就 flush」。也不引入外部组件(不是 Redis / Kafka),就是 DuckDB 里一张表 + 进程内一个协程,和「嵌入式、零运维」的形态一致。

---

## 6. 本地 JSON 镜像:第三份写入,也是第二查询面

DuckDB 是二进制单文件、LanceDB 是列存目录——**都没法 grep**。记忆这种东西,能被最朴素的工具(`grep` / `cat` / `diff` / git)直接看,是可审计、可信任的底线。所以 seekbase 在双引擎之外做**第三份写入:本地 JSON 文件**。

- **声明式,跟 `searchable` 同一路数**:表声明 `files: "cards/{card_id}.json"`(路径模板,列值填充)→ `insert` 自动落一份 **pretty-printed、键序稳定**的 JSON——**写一次就不动**(引擎没有 update);`delete()` 不删文件,把墓碑 `deleted_at` 写进该 JSON(唯一一次引擎代管的重写)。**一行一文件、目录按 id 可导航**——人和 grep 都找得到。
- **追加型大表给 JSONL 模式**:`files: {path: "sessions/{session_id}/rounds.jsonl", mode: "jsonl"}`——append-only 的流水(rounds)一行一条追加,不炸成十万个小文件(v3 的 `rounds.jsonl` 形态原样归位)。
- **写入顺序:文件最先**。`insert()` = ① 写 JSON 文件(canonical 先落地)→ ② 一个 DuckDB 事务(业务行 + outbox 作业,§5)→ ③ consumer 异步兑现向量。任何一步之后崩,**文件都是真相**:行没写上 → 从文件 repair;向量没写上 → outbox replay(§5)。
- **`db.rebuild()`**:通读 files 声明的全部文件 → 重灌 DuckDB + LanceDB。派生层「表丢了能从文件重建」这条不变性,从「各 store 手工兑现」变成 **seekbase 一个内建动作**。
- **没声明 `files` 的表就没有镜像**(纯派生的中间表、日志表不必落盘为文件)。

### 文件是第二查询面:与 SQL 同时进行

镜像不只是「可审计的备份」——它是和 SQL **并行可用的另一个查询面**,两个面随时同查、互不打扰:

- **file 查询无锁、不经 daemon**:`grep` / `cat` / `diff` / git / 任何脚本直接在文件树上跑——daemon 挂着也行、没起也行,**不占 SQL 连接、不被写入阻塞**。这靠两条已焊死的性质兜底:**insert-only** ⇒ 已存在的文件不再变(墓碑那一次除外),读者拿到的结果稳定、可缓存;**原子落盘**(temp + rename)⇒ 并发读永远看到完整文件,不存在半截 JSON。
- **一致性关系明确:文件面 ≥ 行面**。写入顺序文件最先(上面第三条),所以 file 查询**永不缺数据**,至多瞬时超前 DuckDB 一步(crash 后由 repair 收敛);SQL 面强一致、向量面最终一致(§5)——三个面的新旧关系是**固定可推理的**:file ≥ row ≥ vector。
- **两个面能在一条 SQL 里汇合**:DuckDB 原生 `read_json` / glob 外部表——SQL 可以**直接把文件当表查**(`SELECT * FROM read_json('cards/**/*.json')`),用于对账(file 面 vs row 面 diff)、rebuild(§上)、以及派生表还没灌全时的兜底查询。file 即表,不是两个世界。
- **分工**:SQL 面管 join / 聚合 / `search()` / 时光机;file 面管 grep / diff / git 版本化 / 离线拷走整个记忆(目录即备份)。**同一份数据,两种手感,随时并用。**

> 这一步之后,**file-canonical 的「文件」由 seekbase 亲自维护**(v3/v4 是每个 store 手写文件 ops):声明一次,**文件 + 行 + 向量三写全自动**,谁也不会忘了哪一边(§10)。

---

## 7. 时光机:as-of 连接,只见那个时刻之前的世界

**连接时给一个时间点,整个连接就是一台时光机**——所有查询(ORM 链 / SQL / `search()`)只能查出**那个时刻及之前**的数据,像把库倒回当时:

```python
db = await Seekbase.open(data_dir, as_of="2026-06-01T00:00:00Z")   # 只读:6 月 1 日的世界
rows = await db.table("cards").select(...)          # 只见 6/1 前建的卡
hits = await db.table("cards").search("pty tmux")   # 语义检索也只撞 6/1 前的向量
# SQL 面同样生效:memory.talk query --as-of 2026-06-01 "SELECT ..."
```

**机制:谓词改写,不是快照拷贝。**

- **行级两列,seekbase 自动维护**:`created_at`(写入时间,已有)+ **`deleted_at`(墓碑)**——`delete()` 的唯一语义就是**打墓碑**(§2 焊死;向量 doc 同步带上这两个字段)。
- **as-of 连接把每张表换成同名 as-of 视图**:`created_at <= T AND (deleted_at IS NULL OR deleted_at > T)`。用户的 SQL / ORM 一个字不用改,世界自动回到 T。
- **`search()` 同样回溯**:两列进 LanceDB 的 fields,as-of 作为 pre-filter 下推(§4 的机制复用)——检索的是「当时存在的向量」。
- **没有 update,所以 as-of 对所有列严谨**:引擎焊死 insert-only(§2),**不存在「被后来改写污染的历史」**——这正是时光机严谨性的来源,靠结构保证、不靠调用方自觉。会变的值本来就只能落成 append-only 事件表 + 视图现算(reviews 是事件、credence 现算、[mind-data](mind-data.md) 已把计数列整体退役);as-of 视图下从事件重算,任何时刻的值都是当时真值。
- **只读**:时光机连接里不能写(往过去写没有意义);正常连接(不带 `as_of`)行为不变、看到的就是当前态(墓碑行自动滤掉)。

**为什么 memory system 特别需要它**:记忆的**演化本身是一等对象**——「上个月它信什么」(audit)、「这轮治理前后 corpus 差了什么」(回归 diff)、「当时那次召回看到的是哪个世界」(复现)、「记忆质量随时间的曲线」(指标)。没有时光机,这些都只能靠事先留备份。

**代价与出口**:墓碑常驻 = 空间换历史(删除不再释放空间);要空间就显式 `db.vacuum(before=T)`——物理清掉 T 之前的墓碑,**明说这是在丢历史**。文件镜像同规矩:`delete()` 不删 JSON 文件,改写进 `deleted_at` 字段(grep 也能看到「它曾存在」);vacuum 才真删文件。

---

## 8. 为什么像 supabase、又不是 supabase

| | supabase | seekbase |
|---|---|---|
| 形态 | 云 BaaS(Postgres + PostgREST + 一堆服务) | **进程内嵌入库**(两个单文件引擎),零运维、本地优先 |
| 查询体验 | 通用 ORM / 链式构建器 | **一样**(照着这个体验做) |
| 模糊查询 | 无一等支持(pgvector 要自己拼) | **`search()` 一等算子**,自动 embed + 检索 + 组合过滤 |
| auth / realtime / 多租户 | 有 | **不做**(非目标;memory system 是单用户本地栈) |

学 supabase 的是**开发体验**(声明 schema、到处都是同一个链式查询);不学它的是**形态**(不做服务、不做云)。加上它没有的:**语义查询长在 ORM 里**。

---

## 9. 两个形态:本地版(本篇)与云端版(直接换 HTTP)

本篇通体讲的是**本地版**:进程内嵌入,DuckDB + LanceDB + 文件镜像都落在本机目录。但 **seekbase 的端口(ORM 链 + `search()` 算子 + SQL 查询)不绑形态**——**云端版 = 同一个端口走 HTTP**,别的都不用重新发明:

```python
db = await Seekbase.open(data_dir, schema=…, embedder=…)   # 本地版:进程内(本篇)
db = await Seekbase.connect(url, api_key, as_of=…)         # 云端版:同一端口,HTTP 传输(时光机照用)
```

- **调用方代码不变**:链式调用序列化成 HTTP 请求(supabase 本来就是这个形态——PostgREST 干的就是这事);`search()` / SQL 在服务端执行,embedding 也在服务端算(客户端连 embedder 都不用带)。
- **随形态变的只有运维属性**:本地 = 零运维、单用户、进程内一致性;云端 = 多客户端共享一份记忆(多 executor / 多机器天然汇一处)、auth 进场(本地版不做的,云端版必须有)、多一跳延迟。
- **v5 只做本地版**;云端版是**形态预留**,不实现。对现在的约束只有一条:**端口设计不许塞「只有进程内才成立」的假设**(不漏 DuckDB 连接句柄、不假设调用方摸得到数据目录、`flush()` 这类语义要在 HTTP 上也说得通)。

---

## 10. 与 file-canonical 的关系:canonical 不变,派生层升级

[file-canonical 模式](../v3/file-canonical-pattern.md)**不动,且更彻底**:文件仍是权威,数据库仍是**派生索引、可重建**。变的是**谁维护文件**:

```
v3/v4:  files(canonical,各 store 手写文件 ops) → SQLite(手写 SQL)+ LanceDB(searchbase 端口)
v5:     files(canonical,seekbase 经 files 声明自动维护) → DuckDB + LanceDB(同一端口的派生侧)
```

- **文件维护收进 seekbase**(§6):schema 里 `files` 声明一次,写路径自动「文件 → 行 → 向量」三写;各 store 手写的文件 ops 退役;
- 重建 = `db.rebuild()`(读 files → 重灌双引擎),一个内建动作;
- 无 FOREIGN KEY、容忍悬空、表丢了能从文件重建——不变性照旧,统一由 seekbase 兑现。

---

## 11. 与 searchbase 的关系:接棒并吸收

- searchbase 的**纪律全部继承**:业务无关(不认识 card / round)、调用方不见向量、embedder 注入、集合/文档抽象。
- searchbase 的**实现下沉**:`LocalSearchBackend` 那摊(LanceDB 管理、auto_split、超长截断、维护协程)成为 seekbase 向量侧的内部实现。
- searchbase 的**端口退役**:上层不再 import `SearchBackend`;`service/searchbase_schema.py` 那层「业务对象 → 集合」映射,被 §2 的声明式 SCHEMA(`searchable` 列)取代。
- **迁移路径**(粗):seekbase 先以新端口出现 → repository 逐个名词从「手写 SQL + searchbase 双调」搬到 seekbase → 搬完退役 aiosqlite 与 searchbase 端口。SQLite→DuckDB 的数据不用迁(派生层,从文件重建即可)。

---

## 12. 待定

- **ORM API 定形**:链式构建器的完整算子表;返回 dict 还是可选 pydantic 绑定;事务边界(跨引擎原子性已由 §5 outbox 解决;剩 API 上要不要暴露多语句事务)。
- **hybrid search**:`mode="hybrid"`(向量 + BM25)何时做、怎么融分(RRF?)。
- **DuckDB 并发模型**:单写者;daemon 内单连接串行化够不够(outbox consumer 与前台写共用连接怎么调度)。
- **`searchable` 进阶**:多列 search、跨表 search(v4 unified search 那种 cards+insights+rounds 合并按相关排,在 seekbase 里怎么表达——`db.search("…", tables=[…])`?)。
- **时光机细节**:时间用谁的钟(daemon 单调钟?)、粒度(秒够不够)、`as_of` 与 outbox 未兑现作业的边界(T 取到但向量还在队里)、vacuum 策略默认值。
- **迁移节奏**:v5 全新起 or 兼容期双跑;DuckDB 文件放哪、要不要和 LanceDB 同目录成一个「seekbase 实例目录」(像 searchbase 的 `name="v1"` 实例化路数)。

## 与其他 v5 文档的关系

- [README.md](README.md):seekbase 是 **memory system 的数据层**——问题图、session 索引、召回日志都落在它上面;memory system 的「能力」句子(结晶 / 治理 / 召回)最终都翻译成 seekbase 上的读写。
- 嵌入契约(待写):宿主(CC)经 CLI / API 驱动 memory system,不直接碰 seekbase;seekbase 永远是进程内的实现细节。
