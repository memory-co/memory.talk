# test_rebuild_blocks_search

验证 rebuild **进行中** server 进入维护模式 —— search CLI 拿到 503,
rebuild 结束后恢复正常。

## 场景矩阵

| 测试函数 | 验证什么 |
|---|---|
| `test_search_blocked_while_rebuilding` | `app.state.status="rebuilding"` 时 `memory-talk search` 退出码非 0,错误包含 `rebuilding` |
| `test_search_resumes_after_rebuild_completes` | 状态切回 `running` 后,同样的 search 命令成功返回 200 |
| `test_status_still_reachable_during_rebuild` | rebuild 期间 `memory-talk server status` 仍然能拿到 `status=rebuilding`(白名单)|

## 为什么直接翻 `app.state.status` 而不跑真 rebuild

真实 rebuild 在测试里是毫秒级的,无法稳定地"在它进行中"插入 search 调用 —— 这会变成 flaky race。
门禁的契约是"`status != running` 时拒绝非 status 路径",所以**直接置位**就足以验证契约。
真 rebuild 的状态切换路径已经在 `tests/api/test_rebuild_gate.py` 用 monkey-patched spy 验证。

## 覆盖的代码路径

- `api/__init__.py::rebuild_gate` middleware:
  - `status != "running"` 且非 `GET /v2/status` → 503 + `{"error": "rebuilding"}`
- `cli/_http.py::api()` 看到 4xx/5xx → 抛 `ApiError`
- `cli/search.py` 捕获 `ApiError` → 输出 `{"error": <payload>}` JSON,`sys.exit(1)`
