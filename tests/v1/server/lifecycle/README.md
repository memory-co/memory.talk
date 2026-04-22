# Server 生命周期测试

验证 server start → server status → server stop 完整流程。

- start 启动后 status 返回 running + pid
- status 包含数据统计字段
- stop 后 status 返回 not_running
- PID 文件正确创建和清理
