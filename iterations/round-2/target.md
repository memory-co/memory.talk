
# 本轮迭代目标

1. DELTE /api/v1/conversations 能够用来清理会话，可以按照 platform 全部删除。

2. storage.py 参考 java 的 repository 结构，引入DO来解决数据库映射的问题。

3. Conversation 中的session_id变成 conversation_id。

4. 这个导入的报错解决掉 python3 connectors/claude-code/export_sessions.py
API error: 404
