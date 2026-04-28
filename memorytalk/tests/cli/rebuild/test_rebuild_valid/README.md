# test_rebuild_valid

`memory-talk rebuild` 的正常路径。

## 场景矩阵

| 测试函数 | 验证什么 |
|---|---|
| `test_rebuild_returns_counts` | 种 1 session + 1 card 后跑 rebuild,返回 `status=ok` 且 `sessions=1, cards=1` |
| `test_status_back_to_running_after_rebuild` | rebuild 结束后 `app.state.status` 恢复为 `running`,`/v2/status` 也回 `running` |
| `test_search_works_after_rebuild` | rebuild 之后 search CLI 还能正常用 — 索引被正确重建 |

## 覆盖的代码路径

- `cli/rebuild.py` → POST `/v2/rebuild`
- `api/rebuild.py::post_rebuild`:
  - 进入前 `app.state.status = "rebuilding"`
  - try/finally 包裹 service 调用
  - 退出后 `app.state.status = "running"`
- `RebuildService.rebuild()` 全流程:清空 → 从 file-layer 重填 SQLite + LanceDB → 重建 FTS

## 为什么不在这里验证 503 拦截

那是 search 视角的契约,放在 sibling `test_rebuild_blocks_search/` 里。
本场景只看 rebuild 自身能跑通 + 状态机正确归位。
