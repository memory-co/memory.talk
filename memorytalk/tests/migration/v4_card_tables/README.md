# v4_card_tables

**测什么**:迁移 `v4` 在 v3(insight)schema 之上创建 5 张 v4 卡表
(`cards` / `positions` / `reviews` / `card_links` / `card_sessions`),
v3 的 insight 表与之并存;`init_database`(全新装)一次性建出 v3 + v4
两套表。

**不测**:v4 表的列细节 / 索引(归 `tests/repository/v4/schema/`);
LanceDB collection(v4 searchbase 为 no-op,留后续 plan);幂等已由
`CREATE TABLE IF NOT EXISTS` 保证(此处只验「跑完表在」)。
