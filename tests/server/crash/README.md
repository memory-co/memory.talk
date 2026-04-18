# Server 崩溃诊断测试

验证 server 启动失败时错误信息可见。

- server start 失败时返回 `{"status": "failed", "error": "..."}` 而非静默退出
- server status 检测到崩溃日志时返回 `{"status": "crashed", "error": "..."}`
- 无日志时正常返回 `{"status": "not_running"}`
