# sessions — CardSessionStore

## 这个场景在测什么
card↔session 出处:insert + list_for_card(带 position_id / indexes);
一卡多 session;同一卡+session 下不同 position 是两行(PK 含 position_id);
反查 list_cards_for_session(session → 哪些卡);同
(card_id, session_id, position_id) 重复插入幂等。

## 不在这测什么
- 旁白 annotation 写路径 / questions[] 解析 → service plan
- canonical pass 文件 → service plan

## fixture 来源
- `v4db` (`tests/repository/v4/conftest.py`) — `.conn`;场景内一个小 fixture 自建本 store
