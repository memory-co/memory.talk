# query-frame — 把 card / session 以 SQL 直接暴露(v5 设计)

> **状态:设计中。** query-frame 是 [seekbase](seekbase.md) 之上的**查询层**:把 card / session / mark 这些业务对象的查询能力提供出来——但跟 v4 不一样,**不再一个问题开一个端点**,而是**直接把 seekbase 的 SQL 暴露给使用者**。于是它的重心不是「设计接口」,而是**设计表结构**:一套既**继承 IBIS 设计**、又**让使用者自由写 SQL** 的关系框架(frame)。

相关:
- 数据层(双引擎一个端口,SQL 引擎 = DuckDB): [seekbase.md](seekbase.md)
- v5 立意(query-frame 属于 system 的能力层读侧): [README.md](README.md)
- IBIS 底料(card / position / review / link 的语义): [../v4/card.md](../v4/card.md) · [../v4/session-mark.md](../v4/session-mark.md)

---

## 1. 为什么直接暴露 SQL

v4 的教训:**每一种新问法都要新开一个端点**。「列最近的卡」→ `card list`;「这卡从哪些 session 来」→ `GET /cards/{id}/sessions`;「session 的 marks」→ 折进 session read……每个问法 = API + CLI + 渲染 + 测试 + 文档五件套。而使用者(**主要是 AI**)真正想问的是长尾:

- 「反对票最多、但最近 30 天还在被引用的 position」
- 「哪些卡的 issue 相似但从没连过边」(治理要用)
- 「每个 session 产了几张卡、命中率如何」(指标要用)

这些**天然是 SQL**(join / 聚合 / 窗口),而 AI **本来就流利 SQL**——比教它一套自造查询 DSL 便宜得多。seekbase 底下就是 DuckDB(真 SQL 引擎),挡在中间只是折损。所以:

> **表结构就是 API。** query-frame 的契约不是一组端点,而是**一套稳定、文档化的表 / 视图**。schema 设计得好,一切问法都免费;schema 设计得差,再多端点也堵不住。

---

## 2. 边界:SQL 只读;写仍走受治理写路径

**暴露的 SQL 面是只读的**(SELECT-only;无 INSERT / UPDATE / DELETE / DDL)。原因是 IBIS 那套不变性:

- append-only(card / review / mark 只增不改)、credence 不落库、`#…？` 撞库判新——这些**写侧纪律**靠受治理的写路径(system 的动作:mark 提交 / position / review / link / delete)兑现;
- 放开自由写 = 任何一条 `UPDATE` 都能击穿不变性。

所以分工:**问(读)自由,改(写)受治理。** 写路径照走 seekbase 的 ORM(outbox 保原子);query-frame 只管把「问」这半边彻底放开。防护:语句白名单(仅 SELECT / WITH)、行数上限、超时、单只读连接。

---

## 3. 表结构:继承 IBIS 的关系框架

**设计原则**:

1. **一等名词一张表,名词间关系一张表**——不塞 JSON 列,能 join 的都摊平(自由 SQL 的前提);
2. **继承 v4 IBIS 语义不走样**:card=Issue、position=答案(卡内 `p<n>`)、review=表态、link=受治理的边、mark=一次读的逐 round 标注;
3. **派生值进视图不进表**(credence 现算的纪律,SQL 化为 VIEW);
4. **寻址可翻译**:`card_x#p1` / `sess_y#m2` 这种分片寻址,在关系世界就是复合键 `(card_id, position)` / `(session_id, mark)`——两套寻址一一对应。

### 3.1 核心表(继承 v4,列名即契约)

```sql
-- 问题图
cards          (card_id PK, issue, created_at, position_count, link_count)
positions      (card_id, position, claim, scope, forked_from,
                up_count, down_count, neutral_count, review_count, created_at,
                PK (card_id, position))                      -- card_x#p1 ↔ ('card_x','p1')
reviews        (review_id PK, card_id, target, target_kind,  -- 'p1'/'l2' + position|link
                session_id, indexes, argument, comment, created_at)
card_links     (card_id, link, type, target_id, target_type, claim,
                up_count, down_count, neutral_count, review_count, created_at,
                PK (card_id, link))                          -- card_x#l1

-- 出处(provenance)
card_sessions     (card_id, session_id, mark, indexes, created_at,
                   PK (card_id, session_id, mark))
position_sessions (card_id, position, session_id, indexes, mark, created_at)
link_sessions     (card_id, link, session_id, indexes, created_at)

-- 经验侧
sessions       (session_id PK, source, round_count, created_at, …)
rounds         (session_id, idx, role, text, created_at, PK (session_id, idx))
marks          (session_id, mark, last_index, description, created_at,
                PK (session_id, mark))                       -- sess_y#m2
mark_rounds    (session_id, mark, idx, comment,              -- 一次 mark 的逐 round 标注
                PK (session_id, mark, idx))
mark_issues    (session_id, mark, idx, issue, card_id, is_new, indexes)
```

对 v4 的两个升级(为 SQL 而做):

- **`rounds` 进表**:v4 里 round 正文只在 `rounds.jsonl`(文件),SQL 摸不到;v5 把 rounds 作为派生表灌进 seekbase(canonical 仍是文件,§5)——于是「session ↔ 卡 ↔ 轮次正文」能一条 join 打通。
- **mark 摊平成三张表**:v4 的 `marks/m<n>.yaml` 是嵌套 YAML(rounds 里挂 issues);v5 派生层把它摊成 `marks / mark_rounds / mark_issues`——「哪次 mark 的哪一轮产了哪张卡」直接 join,不用读文件解析。

### 3.2 视图:把「现算」和「常用 join」固化

```sql
-- credence 永不落库 → 视图现算(继承 v4 纪律)
CREATE VIEW v_positions AS
  SELECT *, up_count - down_count AS credence FROM positions;
CREATE VIEW v_links AS
  SELECT *, up_count - down_count AS credence FROM card_links;

-- 常用形态预 join,降低长尾查询的门槛
CREATE VIEW v_card_best AS        -- 每卡当前最优答案
  SELECT * FROM v_positions
  QUALIFY row_number() OVER (PARTITION BY card_id ORDER BY credence DESC, created_at) = 1;
CREATE VIEW v_links_in AS         -- 入边反查(target 侧视角)
  SELECT target_id AS card_id, card_id AS from_card, link, type, claim FROM card_links;
CREATE VIEW v_card_provenance AS  -- 卡 ← mark ← session 一步到位
  SELECT cs.card_id, cs.session_id, cs.mark, cs.indexes, m.description, m.created_at
  FROM card_sessions cs JOIN marks m USING (session_id, mark);
```

视图是 frame 的**第二层契约**:表保「摊平的事实」,视图保「别人不该重复推导的口径」(credence 怎么算、最优怎么取、入边怎么反查——口径变了改视图,一处生效)。

### 3.3 语义检索进 SQL:`semantic()` 表函数

seekbase 的 `search()` 算子在 SQL 面以**表函数**出现(DuckDB 注册),返回 `(id, score)` 供 join:

```sql
-- 「语义像这句、且没有任何答案的卡」——ORM 的 search() 在 SQL 里的等价物
SELECT c.card_id, c.issue, s.score
FROM semantic('cards', '为什么 pty 会让用户想到 tmux') s
JOIN cards c ON c.card_id = s.id
WHERE c.position_count = 0
ORDER BY s.score DESC LIMIT 10;
```

于是两个入口一份能力:**ORM 链**(`db.table("cards").search(…)`,程序用)与 **SQL**(`semantic()` join,自由问)底下同一个 LanceDB 检索。

---

## 4. 暴露面:CLI / API 长什么样

```bash
memory.talk query "SELECT … FROM v_card_best WHERE credence < 0 LIMIT 20"   # → markdown 表格 / --json
```

- API:`POST /v5/query {sql}` → 行集(只读校验后直通 DuckDB);
- **schema 自描述**:`memory.talk query --schema`(或 `query "DESCRIBE …"`)把 frame 的表 / 视图 / 列 + 注释吐出来——AI 拿到这份就能自己写一切查询,**这份 schema 文档就是 query-frame 的「API 文档」**;
- v4 的 `read / search / card list` 这类固定问法**降级为 sugar**:内部就是 frame 上的一条预制 SQL(+渲染),不再是独立实现。

---

## 5. 与 file-canonical / seekbase 的关系

- canonical 仍是文件(YAML / JSON / JSONL),**query-frame 的所有表都是派生的**、可从文件重建——这没变;
- 变的是派生层的**完整度**:v4 只派生「够端点用」的瘦索引,v5 派生「够自由 SQL 用」的**全量摊平**(rounds 正文、mark 三表);
- seekbase 管引擎(双引擎、outbox、search 算子),query-frame 管 **schema 契约**(表 / 视图 / 表函数的形状与稳定性)——一个是库,一个是库里的**框架**。

---

## 6. 待定

- **schema 版本化**:表 / 视图是对外契约,怎么演进(加列宽松、改名/删列要 deprecation 期?`frame_version` 表?);
- **只读防护细节**:白名单解析(仅 SELECT / WITH)、`semantic()` 的 embedding 开销限流、行数 / 超时默认值;
- **mark_issues 与 card_sessions 的重叠**:两者都记「mark→card」,前者带轮级细节、后者是聚合出处——留双份还是视图化其一;
- **rounds 全量进表的体积**(66k+ 轮):全灌 or 按需(DuckDB 直读 JSONL 外部表也是路);
- **跨表语义检索**(v4 unified search)在 frame 里的表达:`semantic()` 多集合版 or 一个 `v_search_all`;
- 写路径的 ORM 面(seekbase §12)与本 frame 的读面怎么共用 schema 声明,别声明两遍。

## 与其他 v5 文档的关系

- [seekbase.md](seekbase.md):引擎与端口;query-frame 是它 SQL 面的**业务 schema**。
- [README.md](README.md):能力层的读侧;治理 / 巩固 / 指标那些「corpus 级的问题」,将来都用这套 frame 的 SQL 来问。
- 嵌入契约(待写):宿主(CC)能直接用 `memory.talk query`——这是嵌入面里最通用的一个动作。
