# 重建索引测试

验证删除 SQLite 后，rebuild 能从文件系统完整恢复。

1. 导入 session，创建 card + link
2. 删除 SQLite 文件
3. 执行 rebuild_sync 重建索引
4. 验证 sessions、cards、recall 全部恢复正常
