# positions — PositionStore

## 这个场景在测什么
答案的 SQLite 行 + positions/<pid>.json round-trip;`bump_argument` 按
+1/-1/0 各自加 up/down/neutral_count 且 review_count = 三者之和;非法
argument 报 ValueError;list_for_card 只返回该卡的答案。

## 不在这测什么
- credence 现算排序 → service plan
- review 行本身 → reviews 场景

## fixture 来源
- `v4db` (`tests/repository/v4/conftest.py`) — `.conn` / `.storage`;场景内一个小 fixture 自建本 store
