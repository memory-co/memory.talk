# reviews — V4ReviewStore

## 这个场景在测什么
对 Position 表态的 review 行 insert(带冗余 card_id);list_for_position 按
created_at 倒序且只返回该 position;exists / count。

## 不在这测什么
- bump 到 position 计数(PositionStore.bump_argument)→ service 编排时串起来
- review 文件镜像 → service plan

## fixture 来源
- `v4db` (`tests/repository/v4/conftest.py`) — `.conn`;场景内一个小 fixture 自建本 store
