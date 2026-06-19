# v3 card → insight 迁移(腾名 + 保数据)

> **状态:设计提案,未实施。** v4 要复用 `card` / `card_` 这个名字(命令、SQLite 表、LanceDB collection、id 前缀)。所以现有 v3 那套卡**整体改名 `insight`**,把名字腾出来,同时**一行用户数据都不丢**。这是 [card.md §9](card.md#9-与-v3--insight-的共存与迁移) 步骤一的展开。

改名落成**迁移框架的一个版本**(机制见 [`../v3/migration.md`](../v3/migration.md)):首次启动 lifespan 里 runner catch-up,原地升级。

> **迁移版本号 ≠ 产品代号**:当前 schema 在迁移 **`v2`**(explore 那版),所以**这次改名是迁移 `v3`**(`migrations/v3/{init,up}_{database,searchbase}.py`);v4 新卡表是再后面一版。下文「v3 / 改名后」指**产品语义**。

## 一、改什么(全清单)

| 层 | v3(card) | → 改名后(insight) |
|---|---|---|
| CLI | `memory.talk card` | `memory.talk insight`(只读 + 搜索,见 [`../../cli/v4/insight.md`](../../cli/v4/insight.md)) |
| API | `/v3/cards` | `/v3/insights` |
| SQLite 表 | `cards` / `card_stats` / `card_source_cards` / `reviews` | `insights` / `insight_stats` / `insight_source_cards` / `insight_reviews` |
| LanceDB collection | `cards` | `insights` |
| id 前缀 | `card_<ulid>` | `insight_<ulid>` |
| 文件罐 | `cards/<bucket>/...` | `insights/<bucket>/...` |
| 代码符号 | `service/cards.py` 等 | `service/insights.py` 等 |

**关键:`reviews` 表也要改名 `insight_reviews`**——v4 的 review 要复用 `reviews` 这个名字(target 从 card 改 position),所以 v3 的 reviews 得先让出来。

## 二、SQLite 改名(`migrations/v3/up_database.py`)

SQLite 支持 `ALTER TABLE … RENAME TO`,在一个事务里依次改:

```sql
ALTER TABLE reviews            RENAME TO insight_reviews;   -- 先腾出 reviews 给 v4
ALTER TABLE cards              RENAME TO insights;
ALTER TABLE card_stats         RENAME TO insight_stats;
ALTER TABLE card_source_cards  RENAME TO insight_source_cards;
-- 索引随表名重建(idx_csc_source 等),recall_log / search_log 这类不改名、只改里面的 id(见 §四)
```

整个事务成功才提交;任一步失败回滚(见 [migration.md 失败语义](../v3/migration.md))。

## 三、LanceDB collection:不是「改名」是「拷贝」

`AdminBackend` **没有** `rename_collection`(只有 `create` / `drop` / `copy_rows` / `add·rename·drop_column`,见 [migration.md](../v3/migration.md))。所以 `cards`→`insights`(`migrations/v3/up_searchbase.py`):

```
create_collection('insights')      # 跟 cards 同 schema(flat 布局,只 embed 一列文本 + vector)
copy_rows('cards' → 'insights')    # 行原样搬;若同时做 id 重写(§四),在这步把 id 列改掉
drop_collection('cards')           # 最后删旧的,腾出 cards collection 名给 v4(embed issue)
```

`cards` collection 是 flat 布局、fields schema 空、只 embed `insight` 文本——原样搬即可。

> **更稳的替代:[index-backfill](../v3/index-backfill.md) 从文件罐重灌**。改完 SQLite + 文件罐后,直接对 `insights` collection 跑一次 backfill 从 `insights/<bucket>/*.json` 重建向量,免去 copy_rows 里手工改 id,顺带能换 embedding 维度。代价是重算 embedding(慢、要调 provider)。

## 四、id 前缀重写(`card_<ulid>` → `insight_<ulid>`)——最重的一段

改名只换了「容器名」;**id 本身 `card_<ulid>` 还嵌在一大堆地方**,要一致改写**所有**跨对象引用,否则悬空:

| 引用处 | 形态 | 怎么改 |
|---|---|---|
| `insight_reviews.card_id` | 列 | `card_…` → `insight_…` |
| `insight_source_cards.{card_id, source_card_id}` | 列(自指) | 两列都改 |
| `recall_event.{returned_ids, skipped_ids}` | **JSON 数组**(events.jsonl) | 数组里每个 id 改 |
| `search_log.response_json` | **JSON blob**(嵌完整响应,内含 card id) | blob 内所有 card id 改 |
| `recall_log(session_id, card_id)` | 去重表 | `card_id` 列改 |
| LanceDB `insights` 行的 id 列 | collection 行 | copy 时改,或 backfill 时自然带新 id |
| **文件罐 bucket** | 目录名 | bucket = `card_id[5:7]`(跳过 `card_` 前缀);前缀变 `insight_` 后 bucket = `insight_id[8:10]`,**目录要按新 bucket 重排** |

做法:遍历每张卡建 `old card_<ulid>` → `new insight_<ulid>` 映射(ulid 不变、只换前缀),再扫上表每处替换。

> bucket 取的是「前缀之后的前 2 字符」。`card_` 5 字符、`insight_` 8 字符——前缀长度变了,`[5:7]` → `[8:10]`,bucket 目录跟着重算重排,别漏。

## 五、两段式(降风险开关)

| | 一次到位(本稿倾向) | 分两段 |
|---|---|---|
| 第一段 | 改名 + id 前缀重写,全在迁移 `v3` | 只改名(表 / collection / CLI / API / code),**`card_` id 前缀暂留** |
| 第二段 | — | id 前缀重写单独作为后续一次迁移(归「慢慢下掉」) |
| 好处 | 干净,一步到位 | 第一段不碰海量 id 引用,风险小、能立刻腾出 `card` 命令名 |
| 代价 | 一次性扫所有 id 引用,量大 | insight 数据短期还带 `card_` 前缀——判型不能靠前缀,靠「在 insight 表里就是 insight」 |

开关留给实施时定。

## 六、顺序 / 幂等 / 失败

- **顺序**:database 先(表改名 + id 重写)→ searchbase 后(collection copy / backfill)。两个子系统分开版本化,见 [migration.md 运行时序](../v3/migration.md)。
- **幂等**:迁移记 state,跑过不再跑;catch-up 只补没跑过的版本。
- **失败**:SQLite 改名在事务里(全成或全回滚);LanceDB `create` 幂等、`copy` 可重跑、`drop` 放最后——中途失败重跑安全。若用 backfill,失败重跑 = 重灌,天然幂等。

## 七、改完之后

- **insight 只读可搜**:`memory.talk insight` / `/v3/insights`,老数据继续能 search / read / 回看,但新抽卡只写 v4。
- **`card` / `card_` / `reviews` / `cards` collection 全腾空**给 v4:v4 在干净地基上建 `cards`(问题)/ `positions`(答案)/ `reviews`(对 Position 表态)/ `card_links` / `card_sessions`(见 [card.md §9 步骤二](card.md#9-与-v3--insight-的共存与迁移))。
- **物理隔离共存**:v4 与 insight 不同表、不同 collection、不同前缀,互不干扰。
- 后续可选**把 insight 逐条投影进 v4 图**(card.md §9 步骤三),投影完的 insight 标记已投、不再重复投。

> 相关:迁移框架 [migration.md](../v3/migration.md)、回灌 [index-backfill.md](../v3/index-backfill.md)、v3 卡结构 [`../../structure/v3/talk-card.md`](../../structure/v3/talk-card.md)、改名后命令 [`../../cli/v4/insight.md`](../../cli/v4/insight.md)。
