# schema — v4 DDL shape

## 这个场景在测什么
`create_v4_schema` 建出 5 张表(cards / positions / reviews / card_links /
card_sessions),且列名跟 `docs/structure/v4/` 对齐:cards 带冗余计数
position_count/link_count;positions 带 up/down/neutral/review_count + scope +
forked_from_position_id,且 **没有 credence 列**(现算);card_links 带 target_type。

## 不在这测什么
- 各 store 的读写 round-trip → 各自场景目录
- 迁移 runner 接线 → Plan 2

## fixture 来源
- `v4db` (`tests/repository/v4/conftest.py`) — 临时 SQLite + v4 DDL + LocalStorage(`.conn` / `.storage`)
