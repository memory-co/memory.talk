# query-interface — 把 card / session 以 SQL 直接暴露:一个 reality,多个 mind(v5 设计)

> **状态:设计中。** query-interface 是 [seekbase](seekbase.md) 之上的**查询层**:把 card / session 这些业务对象的查询能力提供出来——但跟 v4 不一样,**不再一个问题开一个端点**,而是**直接把 seekbase 的 SQL 暴露给使用者**。于是它的重心不是「设计接口」,而是**设计表结构**:一套既**继承 IBIS 设计**、又**让使用者自由写 SQL** 的关系框架。且 **session 和 card 拆成不同的库**:**reality(session 库)全局一份共享、对 agent 只读**(全部由 [sync-server](sync-server.md) 同步进来);**mind(card 库)是 IBIS 的基石,每个 [agent](agent.md) 实例一个独立库**,只有所属 agent 可读可写(§2)。

相关:
- 数据层(双引擎一个端口,SQL 引擎 = DuckDB): [seekbase.md](seekbase.md)
- v5 立意(query-interface 属于 system 的能力层读侧): [README.md](README.md)
- IBIS 底料(card / position / review / link 的语义): [../v4/card.md](../v4/card.md) · [../v4/session-mark.md](../v4/session-mark.md)

---

## 1. 为什么直接暴露 SQL

v4 的教训:**每一种新问法都要新开一个端点**。「列最近的卡」→ `card list`;「这卡从哪些 session 来」→ `GET /cards/{id}/sessions`;「session 的 marks」→ 折进 session read……每个问法 = API + CLI + 渲染 + 测试 + 文档五件套。而使用者(**主要是 AI**)真正想问的是长尾:

- 「反对票最多、但最近 30 天还在被引用的 position」
- 「哪些卡的 issue 相似但从没连过边」(治理要用)
- 「每个 session 产了几张卡、命中率如何」(指标要用)

这些**天然是 SQL**(join / 聚合 / 窗口),而 AI **本来就流利 SQL**——比教它一套自造查询 DSL 便宜得多。seekbase 底下就是 DuckDB(真 SQL 引擎),挡在中间只是折损。所以:

> **表结构就是 API。** query-interface 的契约不是一组端点,而是**一套稳定、文档化的表 / 视图**。schema 设计得好,一切问法都免费;schema 设计得差,再多端点也堵不住。

---

## 2. 库的版图:一个 reality(共享),多个 mind(每 agent 一个)

session 和 card **是不同的库**(各自独立的 seekbase 实例),写权属完全不同——**经验与信念的分界就是「谁有权写」的分界**;且 mind **按 agent 实例化**(信念有主人,[agent §1](agent.md)):

| | **[reality 库](reality-data.md)**(session,经验) | **[mind 库](mind-data.md)**(card,信念 / IBIS 基石) |
|---|---|---|
| 份数 | **一份,所有 agent 共享** | **每个 agent 实例一个** |
| 谁写 | 只有 [sync-server](sync-server.md)(ingest;conversations 门给 agent server) | 只有**所属 agent**(受治理写动作) |
| agent 权限 | **只读**(证据不可被管理者改写) | 读写**自己的**;别人的不可见 |

库的定位、不变性、**具体表设计**分别见 [reality-data.md](reality-data.md) 与 [mind-data.md](mind-data.md),本篇不再重复。对查询面而言只需知道:**SQL 全只读**(全部 SELECT-only,写各走各的门),**入口按库分、完全隔离**——一次连接只见一个库(reality 或某个 agent 的 mind),不 ATTACH、不跨库 join、mind 之间互不可见。mind → 证据的关联是 `(type, ref, indexes)` **指针,两步解析**:mind 查指针 → 按 type 去对应的面取原文(session 型 → reality;file 型 → 文件)。这是证据泛化的必然:join 只对「恰好也在库里」的证据型成立,与其偏爱 session 型,不如统一走指针。防护:语句白名单(仅 SELECT / WITH)、行数上限、超时。

---

## 3. schema 契约:原则在此,表在两篇数据文档

表 / 视图的**具体设计**在 [mind-data.md](mind-data.md)(问题图 / proofs 出处 + 视图)与 [reality-data.md](reality-data.md)(sessions / rounds)。本篇只立**共同原则**:

1. **一等名词一张表,关系一张表**——不塞 JSON 列,能 join 的都摊平(自由 SQL 的前提);
2. **继承 v4 IBIS 语义不走样**;寻址 ↔ 复合键一一对应(`card_x#p1` ↔ `(card_id,'p1')`,`sess_y#m2` ↔ `(session_id,'m2')`);
3. **派生值进视图不进表**(credence / 计数现算——视图是「口径的唯一出处」,见 mind-data §3);
4. **表 + 视图就是对外契约**:列名、视图名的稳定性同 API 对待(演进见 §6)。

### 语义检索进 SQL:`search(列, '文本')` 函数

seekbase 的语义检索就是 SQL 里的一个**函数**(按列;每个 `searchable` 列各自一个向量索引),命中分数以 `_score_<列>` 列暴露(单个 search 时附便捷别名 `_score`):

```sql
-- 「语义像这句、且没有任何答案的卡」
SELECT c.card_id, c.issue, _score
FROM v_cards c
WHERE search(issue, '为什么 pty 会让用户想到 tmux') AND c.position_count = 0
ORDER BY _score DESC LIMIT 10;
```

一条 SQL 可有多个 `search()`(搜不同列,各自 `_score_<列>`);结构化谓词下推到向量检索(先过滤后 top-k)。**只有一个入口 = SQL**(seekbase 落地时砍掉了 ORM 链,见 [seekbase §2](seekbase.md))。

---

## 4. 暴露面:CLI / API 长什么样

```bash
memory.talk query "SELECT … FROM v_card_best WHERE credence < 0 LIMIT 20"   # → markdown 表格 / --json
```

- API:`POST /v5/query {sql}` → 行集(只读校验后直通 DuckDB);
- **schema 自描述**:`memory.talk query --schema`(或 `query "DESCRIBE …"`)把 frame 的表 / 视图 / 列 + 注释吐出来——AI 拿到这份就能自己写一切查询,**这份 schema 文档就是 query-interface 的「API 文档」**;
- v4 的 `read / search / card list` 这类固定问法**降级为 sugar**:内部就是 frame 上的一条预制 SQL(+渲染),不再是独立实现。

---

## 5. 与 file-canonical / seekbase 的关系

- canonical 仍是文件(YAML / JSON / JSONL),**query-interface 的所有表都是派生的**、可从文件重建——这没变;
- 变的是派生层的**完整度**:v4 只派生「够端点用」的瘦索引,v5 派生「够自由 SQL 用」的**全量摊平**(rounds 正文、proofs 出处);
- seekbase 管引擎(双引擎、outbox、search 算子),query-interface 管 **schema 契约**(表 / 视图 / 表函数的形状与稳定性)——一个是库,一个是库里的**框架**。

---

## 6. 待定

- **schema 版本化**:表 / 视图是对外契约,怎么演进(加列宽松、改名/删列要 deprecation 期?`frame_version` 表?);
- **只读防护细节**:白名单解析(仅 SELECT / WITH)、`search()` 的 embedding 开销限流、行数 / 超时默认值;
- **跨表语义检索**(v4 unified search)在 frame 里的表达:多表 `search()` 结果 UNION 的预制 SQL or 一个 `v_search_all`;
- 写动作(insert/delete + 业务校验)与本 frame 的读面共用同一份 seekbase SCHEMA 声明——业务层不再有第二份表结构。

## 与其他 v5 文档的关系

- [mind-data.md](mind-data.md) / [reality-data.md](reality-data.md):库的定位与**具体表设计**;本篇是它们之上的查询契约(原则 + 暴露面)。
- [seekbase.md](seekbase.md):引擎与端口;query-interface 是它 SQL 面的**业务 schema**。
- [README.md](README.md):能力层的读侧;治理 / 巩固 / 指标那些「corpus 级的问题」,将来都用这套 frame 的 SQL 来问。
- 嵌入契约(待写):宿主(CC)能直接用 `memory.talk query`——这是嵌入面里最通用的一个动作。
