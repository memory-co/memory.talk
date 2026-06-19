# links — CardLinkStore

## 这个场景在测什么
建一条 card↔card 边:`target_type` 从 target_id 前缀自动派生(card_ →
card,pos_ → position);同 `(card_id, type, target_id)` 重复插入幂等
(INSERT OR IGNORE);list_out 取本卡为主体的边,list_in 反查指向某 id 的边。

## 不在这测什么
- related 无向规范化排序 → service plan
- 五类型白名单校验 → service / API plan(store 不校验类型)

## fixture 来源
- `v4db` (`tests/repository/v4/conftest.py`) — `.conn`;场景内一个小 fixture 自建本 store
