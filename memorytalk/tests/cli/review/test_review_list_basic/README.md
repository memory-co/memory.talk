# test_review_list_basic

`memory-talk review list` 在两次 recall 之后,应该列出两个 session,
按 `last_at` 倒序。

## 验证

- exit 0
- `--json` 输出含 2 个 session
- `last_at` 倒序(后做的 recall 在前)
- 每条含 `round_count`、`cards_injected`、`session_exist`
- 空数据(没跑过 recall)→ `sessions == []`,**不报错**
