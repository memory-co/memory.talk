# Structure (v5)

v5 的数据模型。**在 v5,表结构就是对外契约**([query-interface](../../works/v5/query-interface.md)):使用者直接用 SQL 查这些表 / 视图,所以本目录描述的字段语义**就是 API 文档的主体**。机制与设计推理见 [`../../works/v5/`](../../works/v5/README.md)。

- CLI 契约见 [`../../cli/v5/`](../../cli/v5/README.md) · HTTP 契约见 [`../../api/v5/`](../../api/v5/README.md)

## 库的版图:一个 reality,多个 mind

| 库 | 份数 | 内容 | 谁写 | agent 权限 | 文档 |
|---|---|---|---|---|---|
| **mind**(信念) | **每 [agent](../../works/v5/agent.md) 实例一个** | card / position / review / link / proofs + 视图 | 只有所属 agent(受治理写动作) | 读写自己的;别人的不可见 | [mind.md](mind.md) |
| **reality**(经验) | **全局一份共享** | sessions / rounds / conversations | sync-server(ingest;conversations 门给 agent server) | **只读** | [reality.md](reality.md) |

查询面**完全隔离**:一次连接只见一个库(reality 或某个 agent 的 mind;不 ATTACH、不跨库 join、mind 之间互不可见);mind → 证据的关联靠 `(type, ref, indexes)` 指针**两步解析**(session 型去 reality,file 型去文件)。

## 引擎通用列与不变性(seekbase 焊死,所有表适用)

- **insert-only**:没有 update;`delete` = 打墓碑,**无物理删 / 无 vacuum,历史永久保留**;「改」= 同主键再 insert 新版本(查询视图现算最新版)。每张表带**四个引擎代管字段**(声明式 schema 不写):创建对 `ds`(创建日 `YYYYMMDD`,分区键)+ `created_at`,删除对 `deleted_ds` + `deleted_at`。正常查询自动现算存活版本;[时光机](../../works/v5/seekbase.md)(`ds_end`)按事件重放回到某天;
- **派生值不落表**:会变的值(计数 / credence / round_count)一律视图现算;
- **文件镜像**:每表每天自动一个 `ds=YYYYMMDD/<表>.jsonl`(canonical,可 grep 的第二查询面),file ≥ row ≥ vector 的一致性次序——都是 [seekbase](../../works/v5/seekbase.md) 的通用机制,不逐表重述。

## 证据模式与寻址

- **`(type, ref)` 统一证据模式**(mind 侧一切指向证据源之处):`type` = `'session'`(当前唯一;`'file'` 等预留),`ref` = 该型定位(session 型 = `session_id`),轮级定位用 `indexes`(`'37'` / `'11-15'` / `'3,7,12'`)。软引用、无 FK、容忍悬空。
- **分片寻址 ↔ 复合键**:

| 寻址 | 复合键 | 含义 |
|---|---|---|
| `card_<ULID>` | `cards.card_id` | 一张卡(问题) |
| `card_x#p<n>` | `(card_id, 'p<n>')` | 卡内第 n 个答案 |
| `card_x#l<n>` | `(card_id, 'l<n>')` | 卡内第 n 条边 |
| `sess_…` | `sessions.session_id` | 一个数据 session |
| `sess_…:<indexes>` | `(session_id, idx…)` | session 的某几轮 |
