# v3_insight_rename — migration tests

## 测什么 (what is tested)

- **Rename 3 tables**: `cards`→`insights`, `card_stats`→`insight_stats`, `card_source_cards`→`insight_source_cards` — data preserved (row survives rename).
- **Drop `reviews`**: table and its indexes (`idx_reviews_card`, `idx_reviews_session`, `idx_reviews_explore`) are removed.
- **Move file dir**: `cards/` → `insights/` under `data_root` when old dir exists and new does not.
- **Idempotency**: running `up_database.run` twice does not error.
- **Fresh install**: `v3_init.run` produces the full v3 schema (insight tables, sessions, explores, recall_event, search_log) with no `reviews` and no `cards` table.

## 不测 (what is NOT tested here)

- Searchbase / collection layer (Task 4, separate).
- Application code that reads/writes insights (subsequent tasks).
- FK auto-rewrite behaviour beyond the happy path (SQLite default handles it; no `PRAGMA legacy_alter_table` is set).
