# 前端托管

验证已构建页面和资源可访问，API 路由保持独立，未构建前端时 API 服务仍可运行。不依赖本机已存在的前端产物，也不创建 work 或会话。

```bash
pytest tests/frontend
```

页面构建检查在 `memorytalk/frontend` 执行 `npm run build`。浏览器验证应使用独立的 `MEMORY_TALK_HOME`，覆盖工作创建、子工作、会话切换、认知库读写与历史、用户选择及移动端导航；浏览器终端交互需要已接入 ttyd。
