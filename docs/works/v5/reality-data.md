# reality-data — session 库:经验事实数据(v5 设计)

> **状态:设计中。** [query-interface](query-interface.md) 两库分治里的 **session 库**——**reality(现实)侧**:外部世界如实发生过什么。**只有 [sync-server](sync-server.md) 经 ingest 接口可写**(worker normalize 成标准格式后推入);**对 harness 只读**——经验是证据,证据不可被管理者改写。本篇给出**具体表设计**;对应的信念侧见 [mind-data.md](mind-data.md)。

相关:
- 两库分治的总述(谁读谁写、跨库 join): [query-interface.md](query-interface.md)
- 唯一的写入方(worker → normalize → ingest): [sync-server.md](sync-server.md)
- 引擎(searchable / files 镜像 / 时光机): [seekbase.md](seekbase.md)

---

## 1. 定位与不变性

**reality 库里是事实,不是判断**:哪些 session 发生过、每一轮谁说了什么。四条不变性:

1. **单写入方**:只有 sync-server 的 ingest(`ensure_session` + `append_rounds`)能写——这是**架构上焊死的**(harness 的能力面里根本没有写 reality 的动作),不是约定;
2. **append-only(引擎焊死)**:round 只追加(`idx` 从 1 起严格 +1);session 行**写一次就不动**——`round_count` / `updated_at` 是**派生值**(从 rounds 现算,`v_sessions` 视图),不落列(seekbase 端口没有 update,见 [seekbase §2](seekbase.md));
3. **乐观游标**:游标 = 当前轮数(`max(rounds.idx)` 现算,`v_sessions.round_count`);追加带期望游标,冲突则按服务端游标重拉(sync-server §3 的 push 契约);
4. **内容如实**:落的是 worker `normalize` 后的**标准格式**——格式统一、语义不增删;这里没有总结、没有标注——那些是判断,在 [mind 侧](mind-data.md)(且其工作结构由 harness 自己长,不预制)。

## 2. 表设计

```sql
CREATE TABLE sessions (              -- 写一次就不动(insert-only,seekbase 焊死)
  session_id  TEXT PRIMARY KEY,      -- sess_<…>(worker 归一时从上游会话派生,全局稳定)
  source      TEXT NOT NULL,         -- 哪个 worker:claude-code / codex / openclaw / …
  source_ref  TEXT NOT NULL,         -- 上游定位(原文件路径 / 上游会话 id,溯源用)
  title       TEXT,                  -- 归一时提取(可空)
  started_at  TEXT,                  -- 上游首轮时间
  created_at  TEXT NOT NULL,         -- 首次入库时间
  deleted_at  TEXT                   -- 墓碑(seekbase 时光机;正常不删经验)
);
-- round_count / updated_at 不落列(那是会变的值)→ 视图现算:
CREATE VIEW v_sessions AS
  SELECT s.*, count(r.idx) AS round_count, max(r.created_at) AS updated_at
  FROM sessions s LEFT JOIN rounds r ON r.session_id = s.session_id
                                    AND r.deleted_at IS NULL
  WHERE s.deleted_at IS NULL GROUP BY ALL;

CREATE TABLE rounds (
  session_id  TEXT NOT NULL,
  idx         INTEGER NOT NULL,      -- 1 起、严格 +1 追加(mind 库一切 indexes 指的就是它)
  role        TEXT NOT NULL,         -- user / assistant / tool / system(标准格式统一枚举)
  text        TEXT NOT NULL,         -- 归一后的正文(worker normalize 的产物)
  ts          TEXT,                  -- 上游时间戳(可空,尽力而为)
  meta        TEXT,                  -- 极少量来源侧结构(JSON 字符串;能摊平的别塞这)
  created_at  TEXT NOT NULL,         -- 入库时间
  deleted_at  TEXT,
  PRIMARY KEY (session_id, idx)
);
```

就两张表——reality 刻意简单:**标准格式的字段就是表的列**(worker normalize 产出什么,这里就存什么),上游的花样在 sync-server 的 worker 层已经死掉了,这里不需要为任何来源特化。

**被 mind 库软引用的锚点**(无 FK,容忍悬空):mind 侧统一用 `(type='session', ref=session_id)` 的证据模式指过来(proofs / reviews 引证),轮级则是 `(session_id, idx)`(各处 `indexes` 展开后的轮号)。reality 不知道也不关心谁引用它。

## 3. seekbase 声明(searchable)

| 表 | searchable(自动 embed) |
|---|---|
| sessions | — |
| rounds | `text`(语义搜「当时说过什么」;unified search 的 session 命中源) |

> 文件镜像(`files` 声明)、墓碑、时光机是 **seekbase 的通用机制**([seekbase §6/§7](seekbase.md)),不在业务数据篇重复;路径模板到实现时在 schema 声明里给。

体积注意:rounds 是最大的表(现存 6 万+ 轮、还在长)。全量进表换来「session ⋈ proofs ⋈ card 一条 SQL 打通」(query-interface 的核心收益);若将来体积成负担,DuckDB 直读 JSONL 外部表是现成退路(表变视图,查询面不变)。

## 4. 读它的人

- **harness**:结晶时逐 round 读、review 引证时核对 `indexes`——全部经 query-interface 的只读 SQL;
- **query-interface 使用者**:跨库 join(`rounds ⋈ card_proofs ⋈ cards`)、语义搜 rounds;
- **时光机**(seekbase §7):as-of 连接下,「当时 session 长到哪」精确可答(`created_at` 界定每轮的入库时刻)。

## 5. 待定

- **rounds.meta 的边界**:哪些来源侧字段值得保(tool 调用名?模型名?),原则是「宁可少、能摊平就摊平」;
- **标准格式的版本**:normalize 产物如果演进(加字段),表怎么跟(宽松加列,seekbase 迁移);
- **超长轮正文**:单轮几十 KB 的处理(截断进 embed、全文进表?沿用 searchbase 的 max_text_length 路数);
- **多机汇流**:同一 session 从两台机器推入的合并语义(source_ref 判同?)——云端形态(seekbase §9)前要定。

## 与其他 v5 文档的关系

- [mind-data.md](mind-data.md):判断在那边;那边软引用这边,这边零依赖那边。
- [sync-server.md](sync-server.md):唯一写入方;标准格式(normalize 的产物)= 本篇表列的上游契约。
- [query-interface.md](query-interface.md):本篇的表就是它 SQL 契约的 reality 半边。
