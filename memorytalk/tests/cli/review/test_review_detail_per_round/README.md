# test_review_detail_per_round

跑两轮 recall(同一 session,不同 prompt)→ `review detail` 应该返回:
- 头部:`round_count == 2`
- `rounds`:数组 2 条,按 `round_count` 倒序(round 2 先于 round 1)
- 每条 round 含 `query` / `recalled_at` / `hits`(每个 hit 含 `card_id` + `rank`)
