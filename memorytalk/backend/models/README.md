# models —— 数据形状

Pydantic 模型:API 的请求 / 响应体,也是存储里记录的形状(存的就是 `model_dump()`)。没有方法,只有字段和说明;字段语义的长文在 [`docs/structure/v5`](../../../docs/structure/v5/README.md)。

| 文件 | 模型 |
|---|---|
| `result.py` | `Result[T]` 统一信封 `{data, message, error?}`;`ok(data)` / `fail(error, message)` 两个构造函数,controller 和异常 handler 都用它们 |
| `auth.py` | `AuthStatus`(要不要 setup、这次 token 是谁)/ `SetupRequest` / `LoginRequest` / `LoginResult{token, user}` / `PasswordChange` |
| `users.py` | `User`(档案,含 `role`;密码哈希在记录里但不在模型里)/ `UserCreate`(带初始密码)/ `UserUpdate` / `UserView`(+ 派生统计)/ `UserProfile`(+ 建的 / 动过的 work、最近提交) |
| `work.py` | `Work` / `WorkCreate` / `WorkUpdate` / `WorkNode`(带 children);画布 `Canvas{version, columns[]}` / `Column{id, panels[], collapsed}` / `Panel{session, collapsed}` / `CanvasPut`;会话 `Session` / `SessionCreate` / `SessionView`(+ alive / window / handle);`Round` / `Event` / `WorkUser` / `WorkUsers` |
| `work_server.py` | server 那一侧的形状:`ParsedUri` / `Window`(窗)/ `HandleInfo`(把手)/ `Live`(open 之后交回来的东西)/ `WorkServerInfo` / `Handle` Protocol / `WorkServerError` |
| `metas.py` | `LayerInfo`(含 `protocol` 字典)/ `TreeView` / `TreeItem` / `CheckResult` / `Obj` / `ObjWrite` / `Revision` / `RecentItem` / `RecentPage` / `Manager` / `ManagerPut` / `InboxItem` |
| `search.py` | `SearchHit{kind, id, title, snippet, …}` / `SearchResult{query, hits, counts}` |
