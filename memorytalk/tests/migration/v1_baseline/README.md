# v1_baseline

## 测什么

`migrations/v1/init_*` 的全量快照能从空白建出 v1 的形状,且重复运行
不出错:

- **database** —— `init_database.run()` 在一个空 SQLite 上跑完之后,
  v1 该有的表全在,关键列(`tags` / `location` / `indexed_round_count`
  /  `recall_count` 已经不在 `card_stats` 里 etc.)都对得上;再跑一
  次不报错
- **searchbase** —— `init_searchbase.run()` 在 fresh backend 上是
  no-op(backend 构造器已经按声明的 schema 建好了),但跑完后 `cards`
  / `rounds` collection 形状仍是 v1(`id` 不是 `card_id`,`rounds`
  有 `id` / `_base_id` / `_chunk`)

## 不测什么

- 从 0.8.x 形状搬上来 —— 在 `v1_upgrade_from_081/`
- runner 决定调不调 init —— 在 `runner_modes/`
- 跟 lifespan 拼装 —— 在 `lifespan_integration/`

## fixture

数据库测试用 `aiosqlite.connect(":memory:")`,不挂项目 fixture。
searchbase 测试构造一个临时 `LocalSearchBackend`(`_DummyEmbedder`
+ `tmp_path/vectors`),局部定义,不依赖 searchbase 测试的 conftest。
