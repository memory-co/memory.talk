# 场景：数据库选型的记忆

对应 stories/s1/01-database-decision.md。

完整流程：sync 导入会话 → sessions list 确认 → sessions read 读取 rounds → cards create 创建精简记忆卡片 → recall 检索到这张卡片 → status 验证计数。

测试材料：`sessions/sess_db_decision.jsonl` — 模拟 Claude Code 的向量库选型对话。
