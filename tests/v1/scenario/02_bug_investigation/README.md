# 场景：Bug 排查的记忆

对应 stories/s1/02-bug-investigation.md。

完整流程：导入两个 session（选型 + bug 排查） → 创建选型 card → 创建 bug card 并关联到选型 card → 验证 links 跨 card 关联 → 验证 card 内容和 TTL。

测试材料：
- `sessions/sess_db_decision.jsonl` — 选型对话
- `sessions/sess_bug_investigation.jsonl` — LanceDB NFS 阻塞 bug 排查对话
