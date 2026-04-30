# test_recall_first_call

第一次跑 `memory-talk recall <new_session> <prompt>`,session 未存在于 v2 里。
预期:
- 不报错(recall 不要求 session 在 v2 里存在)
- recall 表新插入一行,round_count = 1
- recall_hit 表写入 top-K 命中记录
- stdout 是 bash code-block 形式的 Markdown(默认 top_k=3)
- 用 `--json` 验证 `round_count`、`recalled` 列表、`skipped_already_recalled=[]`

## 验证

- exit code 0
- `--json` 输出含 `round_count == 1`
- `recalled` 长度 ≤ 3,每条有 `card_id` + `summary`
