# 场景：一次意外的回忆

对应 stories/s1/03-recall-and-connect.md。

完整流程：基于两个 session 创建两张关联 card → recall 搜索 → 验证 card TTL 被 recall 刷新 → 通过 cards get --link-id 验证 link TTL 被刷新 → status 验证计数。

测试材料：
- `sessions/sess_db_decision.jsonl` — 选型对话
- `sessions/sess_bug_investigation.jsonl` — bug 排查对话
