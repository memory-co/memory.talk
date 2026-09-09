# v3 card → insight 迁移(腾名)

> **状态:设计提案,未实施。** v4 复用 `card` / `cards` / `reviews` 这些名字(命令、SQLite 表、LanceDB collection、文件罐、`card_` id 前缀)。所以现有 v3 那套卡**改名 `insight`** 把名字腾出来。落成迁移框架的一版(机制见 [`../v3/migration.md`](../v3/migration.md)),首启动 catch-up 原地升级。**迁移的数据 / schema 变换全部写在 `migrations/` 内**;v3 应用代码在同一个 plan 里同步指向新名字(见 §五)。

> **迁移版本号 ≠ 产品代号**:当前 schema 在迁移 `v2`(explore),所以这次改名是迁移 **`v3`**;v4 建新卡表是迁移 **`v4`**。

## 关键取舍(已定)

- **`reviews` 直接 DROP,不改名**:v3 的 review 数据从没真正用起来——不迁移、不留 `insight_reviews`。DROP 掉就把 `reviews` 名字腾给 v4(v4 的表态落在 Position 上)。v3 的 review 功能(`service/reviews.py` / `api/reviews.py` / `cli/review.py` + `CardStore` 的 review 方法 + `card_stats` 的 review 计数写路径)一并退役。
- **`card_` id 前缀保留(两段式)**:insight 行继续带 `card_<ulid>` id,**这一版不重写 id 前缀**。靠 `/v3` vs `/v4` 路由命名空间区分(`parse_id` 只在各自 router 内解析,**没有全局「解析任意 id」路径**),所以 insight 的 `card_` 和 v4 新卡的 `card_` 不冲突。彻底改成 `insight_` 前缀留作后续可选迁移(「慢慢下掉」),本稿不做。
- **collection 改名用目录级 rename,不重灌**:见 §三(`AdminBackend` 没有 `copy_rows`,但目录 rename 零成本)。

## 一、改什么(全清单)

| 层 | v3(card) | → 改名后 |
|---|---|---|
| SQLite 表 | `cards` / `card_stats` / `card_source_cards` | `insights` / `insight_stats` / `insight_source_cards`(RENAME) |
| SQLite 表 | `reviews` | **DROP**(未用;不留 `insight_reviews`) |
| LanceDB collection | `cards` | `insights`(目录级 rename,§三) |
| 文件罐 | `cards/<bucket>/...` | `insights/<bucket>/...`(顶层目录 move;per-card 目录名仍 `card_<ulid>`,id 不变) |
| id 前缀 | `card_<ulid>` | **不变**(两段式,保留 `card_`) |
| CLI | `memory.talk card` | `memory.talk insight`(只读 + 搜索) |
| API | `/v3/cards` | `/v3/insights` |
| 代码符号 | `repository/cards.py` `CardStore` 等 | `repository/insights.py` `InsightStore` 等(§五) |

## 二、SQLite(`migrations/v3/up_database.py`)

一个事务内:

```sql
DROP TABLE IF EXISTS reviews;                            -- 未用,直接丢,腾名给 v4
ALTER TABLE cards             RENAME TO insights;
ALTER TABLE card_stats        RENAME TO insight_stats;
ALTER TABLE card_source_cards RENAME TO insight_source_cards;
```

- 现代 SQLite(`legacy_alter_table` 关)在 RENAME 时**自动改写其它表 FK 定义里的引用**(`insight_stats` 的 `FOREIGN KEY … REFERENCES cards` → `insights`);先 `DROP reviews` 就不用管它那条 FK。
- 索引(`idx_cards_created` 等)保留、仍指向改名后的表;可选一并 rename 求整洁。
- gate:`DROP … IF EXISTS` + ALTER 前用 `PRAGMA table_info` 探测,重跑幂等。

## 三、LanceDB collection:加 `rename_collection` 原语,目录级改名

一个 LanceDB collection = `vectors/<name>.lance/` 一个目录。改名 = 目录 / 表 rename,**不动数据、不重 embed、零搬运**。现有 `AdminBackend` 没有 collection 改名(也没有 `copy_rows` / 读全表),所以给它加一个原语:

```python
# searchbase admin(新增)
async def rename_collection(self, old: str, new: str) -> None: ...
# LocalAdminBackend:LanceDB db.rename_table(old, new)(或 rename .lance 目录 + 更新内部登记)
```

迁移里一行(`migrations/v3/up_searchbase.py`):

```
await admin.rename_collection('cards', 'insights')   # 腾出 cards 给 v4(embed issue)
```

比 create+copy 或 backfill 重灌都干净,且整段在 `migrations/` 内(只调 admin 原语)。**加原语是迁移框架的合理支撑(可复用),不算「外溢」**——业务 service 仍然永不碰 admin。

## 四、文件罐:顶层目录 move(`cards/` → `insights/`)

`card_` id 不变(两段式),所以 per-card 目录名(`card_<ulid>`)和 bucket(ULID 前 2 字符)都不变——**只把顶层目录 `cards/` 整体 move 成 `insights/`**。

- **框架扩展**:`migrations/v3` 需要文件系统句柄。runner 已持有 `_data_root`,把它作为「files」子系统句柄传给迁移(或给 migration 传 `Config`)。**文件 move 的逻辑写在 `migrations/v3/` 内**,不落到 service / 启动 hook(对比 v2 的 `last_round_update_time` backfill 是在 `api/__init__` 里跑的——这次不走那条外溢老路)。

## 五、v3 应用代码同步(同一个 plan 交付)

迁移把存储改了名,v3 代码必须同步指向新名字、并退掉 review,否则运行时断。**这部分是应用代码改动(不是迁移逻辑),但和迁移在同一个 plan 里交付**,使「迁移跑完 → v3(insight 只读)立即可用、整套测试绿」:

- `repository/cards.py` → `insights.py`:类 `CardStore` → `InsightStore`;所有 SQL 表名 `cards` / `card_stats` / `card_source_cards` → `insight*`;文件 `PREFIX = "insights"`;**删 review 方法**(`append_review_mirror` / `bump_review` / `reviews.jsonl` / `bump_review` 的 `card_stats` 写)。
- `service/searchbase_schema.py`:`CARDS` 常量值 → `"insights"`。
- `service/cards.py` → `insights.py`;`api/cards.py` → `api/insights.py` 挂 `/v3/insights`;`cli/card.py` → `cli/insight.py`,命令名 `insight`(只读 + 搜索)。
- **退役 review**:删 `service/reviews.py` / `api/reviews.py` / `cli/review.py` / `schemas` 里 Review 的写路径 / 对应测试;`insight_stats` 的 `review_*` 列变 vestigial(留着不写)。
- 既有 v3 测试套随之更新到新名字 / 删掉 review 测试 —— **跑绿就是安全网**。

## 六、顺序 / 幂等 / 失败

- **顺序**:database(DROP + RENAME)→ files(目录 move)→ searchbase(`rename_collection`)。各子系统独立版本化 + state 记录,见 [migration.md](../v3/migration.md)。
- **幂等**:`DROP IF EXISTS`、ALTER 前探测列、`rename_collection` 前 `list_collections` 探测、目录 move 前判存在;跑过不再跑。
- **失败**:SQLite 在事务里(全成 / 全回滚);目录 move、`rename_collection` 单步可重跑。

## 七、改完之后

- **insight 只读可搜**:`memory.talk insight` / `/v3/insights`,老数据继续能 search / read。
- **`card` / `cards` / `reviews` / `cards` collection / `cards/` 目录全腾空**给 v4(下一版迁移 `v4` 建 v4 表,见 [card.md §9 步骤二](card.md#9-与-v3--insight-的共存与迁移))。
- **物理隔离共存**:v4 与 insight 不同表 / collection / 目录;id 前缀暂时都 `card_`,靠 `/v3`·`/v4` 路由区分。
- 后续可选:把 insight 投影进 v4 图(card.md §9 步骤三);以及把 insight 的 `card_` id 彻底改成 `insight_`(两段式的第二段)。

> 相关:迁移框架 [migration.md](../v3/migration.md)、v3 卡结构 [`../../structure/v3/talk-card.md`](../../structure/v3/talk-card.md)、改名后命令 [`../../cli/v4/insight.md`](../../cli/v4/insight.md)。
