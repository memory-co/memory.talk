# seekbase — 数据库抽象层(v5 设计,已对齐实现)

> **状态:已实现**——独立 pip 包 **`seekbase`**(独立仓库,M1–M4 核心完整:SQL query + `search()` + `ds` 时光机、异步 ticket 写、文件镜像 + rebuild、向量侧 outbox、嵌入与 server 双形态)。本篇是**概念层**(为什么、角色、不变性);工程细节与逐接口契约见该仓库的 `DESIGN.md` 与 `docs/`(api: query / insert / delete / admin / setup;works: store / schema / time_machine)。
>
> 定名 **seekbase**(seek = 既查〔结构化〕又寻〔语义〕的底座)。定位与 [searchbase](../v3/searchbase-extraction.md) 同一路数、**更进一步**:searchbase 把「向量检索」封成一个端口;seekbase 把**整个数据层**封成一个端口——**SQL 直通**,且**语义 `search()` 是 SQL 里的一等函数**;底层 **DuckDB + LanceDB + 文件镜像**,焊死 insert-only,自带 outbox 与时光机。

相关:
- searchbase(它的前身与被吸收对象): [../v3/searchbase-extraction.md](../v3/searchbase-extraction.md)
- v5 立意(seekbase 是 memory system 的数据层): [README.md](README.md)
- file-canonical 模式(与本层的关系见 §10): [../v3/file-canonical-pattern.md](../v3/file-canonical-pattern.md)

---

## 1. 问题:两条栈、手写 SQL、search 是外挂

v4 的数据层是**两条互不认识的栈**:

```
repository/*.py  ──手写 SQL──▶  SQLite(aiosqlite,结构化)
service/*.py     ──端口调用──▶  searchbase(LanceDB,向量)
```

- **每个名词一个 store、每个 store 手写 SQL**——加一列 = 改 DDL + insert + get + list + 迁移,四五处手工同步;
- **结构化查询和语义查询是两个世界**:「语义像这句、且 kind=issue、且最近 30 天」要两边手工拼;
- **写入双写靠自觉**:每个 service 都要记得「插了行还要 upsert 向量」,漏一边 = 数据漂移。

这三个痛点是同一个病:**没有一个统一的数据端口**。seekbase 把 searchbase 证明过的「封端口」手法推广到整个数据层。

## 2. 它是什么:SQL 端口 + `search()` 一等函数 + 焊死 insert-only

**一句话:一个数据端口 = SQL 读 + 异步写,语义检索长在 SQL 里,引擎强制只增。**

```python
db = await Seekbase.open("./data", schema=SCHEMA, embedder=embedder)

# ── 读:就是 SQL(结构化 + 语义 + 时光机,一个接口)──────────
rows = await db.query(
    "SELECT card_id, issue, _score FROM cards "
    "WHERE search(issue, '为什么 pty 会让用户想到 tmux') AND kind = ? "
    "ORDER BY _score DESC LIMIT 10",
    params=["issue"],
)

# ── 写:异步 ticket(insert / delete,没有 update)──────────
ticket = await db.insert("cards", {"card_id": "c1", "issue": "…", "kind": "issue"})
await db.wait(ticket)                                  # 要读己之写就等票
await db.delete("cards", where="card_id = ?", params=["c1"])   # 仅打墓碑,永不物理删
```

- **读 = SQL,不设 ORM 链**:落地时把设计稿里的链式构建器砍掉了——SQL 本身就是通用查询语言(AI 流利、人也流利),链式只是冗余包装。端口的公共面就三件事:`query` / `insert` / `delete`(+ ticket 的 `wait` / `write_status`、管理面 `rebuild` / `close`)。
- **`search(列, '文本')` 是 SQL 函数,不是另一条 API**:`列` 是声明过的 `searchable` 列(**每个可搜列各自一个向量索引**);出现它时 seekbase 自动 embed → 撞那一列的索引 → 与其余谓词组合,暴露 `_score_<列>`(单个 search 时附便捷别名 `_score`)。一条 SQL 可有多个 `search()`(搜不同列)。**调用方永远不见向量、不算 embedding**——纪律从 searchbase 继承。
- **写是异步 ticket**:`insert` / `delete` 返回 ticket,立即返回;落库进度用 `wait(ticket)` / `write_status(ticket)` 查。设计稿里的 `flush()` 由**按票等**取代(更细粒度)。
- **焊死的不变性:只能增、不能改、不能物理删。** 端口没有 `update` / `upsert`;`delete()` 唯一语义 = 打墓碑;**「改」= 同主键再 insert 一个新版本**(不必先删——多版本追加,查询视图现算最新版,§7);**没有 vacuum,历史永久保留、零例外**(设计稿曾留 vacuum 出口,实现里砍掉了:丢历史的口子一开,时光机的严谨就只剩纪律而非结构)。
- **schema 声明式,一处声明处处推导**(**有序列表**,不是 dict):

```python
SCHEMA = [
    { "table": "cards",
      "columns": [ {"name": "card_id", "type": "str"},
                   {"name": "issue",   "type": "str"},
                   {"name": "kind",    "type": "str"} ],
      "primary": "card_id",
      "searchable": ["issue"] },        # ← 写入自动 embed;SQL 里 search(issue, …) 可用
]
```

从这一处推导 DDL / 双引擎同步 / 文件镜像 / 时光机字段——**时光机的四个引擎代管字段(`ds` / `created_at` / `deleted_ds` / `deleted_at`)不在 schema 里写**,引擎自动加(§7)。上层从此不手写 SQL DDL、不手写文件 ops、不手写向量接线。

## 3. 底层:一个端口 = 三写(files / DuckDB / LanceDB)

```
                    Seekbase(端口:query / insert / delete)
          ┌───────────────────┼───────────────────┐
       files                DuckDB              LanceDB
    (canonical)          (结构化派生)          (向量派生)
   可 grep/diff/git     过滤·聚合·join·时间窗   embed·ANN(每 searchable 列一个索引)
          └────── 派生自 files,可 rebuild() 整体重灌 ──────┘
```

- **files = canonical**(真相,§6);**DuckDB / LanceDB 都是派生索引、可重建**;
- **一个实例 = 一个目录**:`<data_dir>/{files/, duck.db, lance/, _meta.json}` ——**拷走目录 = 拷走整个库**;
- **业务无关**(searchbase 纪律):包里不认识 card / session、不读任何 Config,只收注入的 `data_dir` / `schema` / `embedder`(自带 `ApiEmbedder`,OpenAI 兼容 `/embeddings`;本地模型 embedder 记 TODO);
- 双引擎同步是内政:**上层没有「双写」这个概念**。

## 4. search() 与结构化谓词怎么组合

`search(列, …)` 和普通谓词写在同一条 SQL 里时(内部,调用方无感):

1. **过滤下推优先**:能翻成向量侧 filter 的结构化谓词直接下推——在过滤后的子集上做 ANN,保「先过滤后取 top-k」(不犯 post-filter 返回空的病);
2. 下推不了的谓词:向量侧取放大候选,回 DuckDB 精过滤再截;
3. 不带 `search()` 的 SQL:纯 DuckDB,不碰向量侧;
4. 排序:`_score_<列>` 是普通列,`ORDER BY` 随意。

## 5. 写路径:异步 ticket + 内建 outbox

**跨引擎没有事务**(DuckDB 的事务包不住 LanceDB),解法仍是 **transactional outbox**,叠加 ticket 化:

```
insert(table, rows) → 立即返回 ticket
        │
        ▼(引擎内,按序)
  ① append 到 files(canonical 先落地,§6)
  ② 一个 DuckDB 事务:append 行事件 + _outbox 作业
  ③ consumer 异步兑现向量(embed → LanceDB upsert)
        │
  wait(ticket) / write_status(ticket) ─→ 各阶段状态
```

- **at-least-once + 按 pk 幂等 = 收敛**;崩溃 = 重放(pending 作业和行事件同事务落的),不需对账;彻底坏了还有 `rebuild()`(从 files 整体重灌,§6);
- **一致性次序固定可推理:file ≥ row ≥ vector**——要读己之写,`wait(ticket)`;结构化查询在票结清后强一致,向量侧最终一致。

## 6. 文件镜像:canonical、可 grep、第二查询面

DuckDB 是二进制、LanceDB 是列存目录——**都没法 grep**。所以 canonical 落在**纯文本 JSONL**:

```
<data_dir>/files/
  ds=20260705/               # 顶层 = 日期分区(写入日)
    cards.jsonl              # 当天写过这张表就有;一行一条 compact JSON,append-only
    rounds.jsonl
  ds=20260706/
    cards.jsonl
```

- **形态只有一种:每表每天一个 append 日志**(设计稿曾设计「一行一文件 + 路径模板声明」——实现里砍掉了:百万行会炸成百万文件;每表每天一个 jsonl 后扇出问题从根上消失,**也不再需要 `files:` 声明**,每张表自动有镜像);
- **主键不进文件路径**:pk 只在派生层做行标识;canonical 点查靠 `grep '"card_id":"c1"' files/ds=*/cards.jsonl`,定位行走 DuckDB;
- **删除也是一条追加的墓碑事件**(文件真·纯 append,零例外);重复主键 = 再 append 一行(新版本);
- **第二查询面**:grep / cat / diff / git 直接在文件树上跑,不经 daemon、不被写入阻塞(append-only ⇒ 已写内容不变;逐行 append ⇒ 读者不见半条记录);DuckDB `read_json` 还能把文件当表查(对账 / 兜底);
- **`rebuild()`** = replay files → 重灌 DuckDB + LanceDB。「表丢了能从文件重建」从各 store 手工兑现变成**一个内建动作**。

## 7. 时光机:`ds` 日期分区 + 事件重放

**连接不变,查询带时间窗**:`query(sql, ds_start=…, ds_end=…)`(`YYYYMMDD`,粒度 = 天)。**只给 `ds_end` = 时光机**(回到那天结束时的世界)。

- **四个引擎代管字段**(声明式 schema 不写,引擎自动加):创建一对 `ds`(创建日,分区键)+ `created_at`(精确时刻);删除一对 `deleted_ds` + `deleted_at`(活行为 NULL)。`_ds` 管分区与 as-of 判定,`_at` 管日内精度与审计;
- **事件重放,不是单行谓词**:派生 DuckDB 是**纯 append 事件表**(每次写 = put 或 del 事件,带单调 `_seq`)。「as-of D」= 对每个主键重放 `day ≤ D` 的事件、按 `_seq` 取最新——put 则可见(数据 = 那一版),del 则隐藏。**对任意 create / delete / re-insert 历史都正确**(单行就地打 `deleted_ds` 的写法在「删了又重插」时会丢旧版本);SQL 上就是一个窗口视图,`search()` 复用它;
- **`ds_start`** 是额外的创建下界(存活版本再滤 `ds ≥ ds_start`);审计视图(某窗口创建过的版本,不管后来删没删)直接在 SQL 里 `WHERE ds BETWEEN …`;
- **没有 update,所以 as-of 对所有列严谨**——不存在「被后来改写污染的历史」;会变的值本来就只能落成事件 + 视图现算([mind-data](mind-data.md) 的计数列退役正是为此);
- **历史永久保留**(无 vacuum):空间换的是「任何一天都能诚实回放」。

**为什么 memory system 特别需要它**:记忆的演化是一等对象——「上个月它信什么」(audit)、治理前后 diff(回归)、复现某次召回当时的世界、质量随时间曲线(指标)。

## 8. 为什么像 supabase、又不是 supabase

| | supabase | seekbase |
|---|---|---|
| 形态 | 云 BaaS(Postgres + PostgREST) | **嵌入库 / 自托管 server 二选一**(§9),零运维、本地优先 |
| 查询 | ORM / 链式构建器 | **直接 SQL**(声明 schema,一处推导) |
| 模糊查询 | 无一等支持(pgvector 自己拼) | **`search()` 长在 SQL 里**,自动 embed + 检索 + 组合过滤 |
| auth / realtime / 多租户 | 有 | 不做(server 形态只有可选 bearer token) |

学 supabase 的是**声明 schema、一个端口进出所有数据**的体验;不学它的形态;加上它没有的:语义查询是 SQL 的一部分。

## 9. 两种使用形态:嵌入 与 server(都已实现)

```python
db = await Seekbase.open("./data", schema=…, embedder=…)     # 嵌入:进程内
db = await Seekbase.connect("http://host:8000", api_key=…)   # server:HTTP 客户端
```

- **调用代码逐字节相同**:`query` / `insert` / `delete` / `wait` 一个字不用改,变的只有拿句柄这一步;**错误过线保型**(server 抛的 `ReadOnlyError`,client 收到的还是 `ReadOnlyError`);
- **server = `seekbase_server(db)`**:零依赖手写 ASGI app(`/v1/query` `/v1/insert` `/v1/delete` `/v1/writes/{ticket}` `/v1/rebuild` `/v1/health`),**ASGI runner 由宿主外部注入**(uvicorn / hypercorn / 挂进已有应用),seekbase 不绑定 runner;鉴权 = 可选 bearer token;
- 设计稿的「云端版预留」就此兑现为 server 形态:多客户端 / 多进程共享同一实例(多 executor / 多机器汇一处)走它;时光机(`ds_end`)在 HTTP 上一样;
- 当年立的约束应验了:**端口从没塞过进程内假设**,所以换传输不换契约。

## 10. 与 file-canonical 的关系:canonical 不变,由 seekbase 亲自维护

```
v3/v4:  files(canonical,各 store 手写文件 ops) → SQLite(手写 SQL)+ LanceDB(searchbase 端口)
v5:     files(canonical,seekbase 自动维护:每表每天 jsonl) → DuckDB + LanceDB(同一端口的派生侧)
```

- 文件维护收进 seekbase(§6):**自动、无需声明**;各 store 手写的文件 ops 退役;
- 重建 = `rebuild()`;无 FOREIGN KEY、容忍悬空、表丢了能从文件重建——不变性照旧,统一由 seekbase 兑现。

## 11. 与 searchbase 的关系:接棒并吸收

- **纪律全部继承**:业务无关、调用方不见向量、embedder 注入;
- **实现下沉**:LanceDB 管理成为 seekbase 向量侧内政(每 `(表, searchable 列)` 一个 `vec_<表>__<列>` 索引);
- **端口退役**:上层不再 import `SearchBackend`;「业务对象 → 集合」映射被声明式 SCHEMA(`searchable` 列)取代。

## 12. 待定(工程层,详见 seekbase 仓库 DESIGN §10)

- **本地模型 embedder**(`[st]` extra,sentence-transformers)——记 TODO,当前用注入 / `ApiEmbedder`;
- **hybrid search**(向量 + BM25 融分)——接口上留 `search()` 的演进空间;
- **并发细节**:DuckDB 单写者下 consumer 与前台写的调度;server 形态多客户端的写队列;
- **`ds` 粒度**:天粒度对记忆场景够用(结晶 / 治理以天为节奏);要日内精度用 `created_at` 二级过滤——若未来不够再议。

## 与其他 v5 文档的关系

- [query-interface.md](query-interface.md):在本端口的 SQL 面上定业务 schema 契约(mind / reality 的表与视图);
- [mind-data.md](mind-data.md) / [reality-data.md](reality-data.md):具体表设计;时光机四字段由本层代管,数据篇不声明;
- [agent.md](agent.md):每个 agent 的 mind 库 = 一个 seekbase 实例(目录);reality 也是一个实例——server 形态天然支撑多 agent 共享 reality。
