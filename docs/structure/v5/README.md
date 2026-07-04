# Structure (v5)

v5 的数据模型。**在 v5,表结构就是对外契约**([query-interface](../../works/v5/query-interface.md)):使用者直接用 SQL 查这些表 / 视图,所以本目录描述的字段语义**就是 API 文档的主体**。机制与设计推理见 [`../../works/v5/`](../../works/v5/README.md)。

- CLI 契约见 [`../../cli/v5/`](../../cli/v5/README.md) · HTTP 契约见 [`../../api/v5/`](../../api/v5/README.md)

## 两个库(分治)

| 库 | 内容 | 谁写 | harness 权限 | 文档 |
|---|---|---|---|---|
| **mind**(信念) | card / position / review / link / proofs + 视图 | 只有 harness(受治理写动作) | 可读可写 | [mind.md](mind.md) |
| **reality**(经验) | sessions / rounds | 只有 sync-server(ingest) | **只读** | [reality.md](reality.md) |

查询可见性**不对称**:mind 连接附带 reality(只读,跨库 join 在信念侧);reality 连接独立、不见 mind——与写权属的不对称同构。

## 引擎通用列与不变性(seekbase 焊死,所有表适用)

- **insert-only**:没有 update;`delete` = 打墓碑。每张表都有 `created_at`(写入时刻)与 `deleted_at`(墓碑,NULL = 活着);正常查询自动滤墓碑,[时光机](../../works/v5/seekbase.md)(as-of)按这两列回放;
- **派生值不落表**:会变的值(计数 / credence / round_count)一律视图现算;
- **文件镜像**:表数据同步落本地 JSON(可 grep 的第二查询面),file ≥ row ≥ vector 的一致性次序——都是 [seekbase](../../works/v5/seekbase.md) 的通用机制,不逐表重述。

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
