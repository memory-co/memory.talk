# cards — V4CardStore

## 这个场景在测什么
卡的 SQLite 行 + card.json 文件 round-trip;position_count / link_count
两个冗余计数能 +1;exists / count;list_cards 按 created_at 倒序 + total。

## 不在这测什么
- Position / review / link / session → 各自场景
- 多表原子 create 编排 → service plan

## fixture 来源
- `v4db` (`tests/repository/v4/conftest.py`) — `.conn` / `.storage`;场景内一个小 fixture 自建本 store
