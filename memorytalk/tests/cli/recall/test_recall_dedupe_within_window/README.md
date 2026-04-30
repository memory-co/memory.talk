# test_recall_dedupe_within_window

同一个 session 连续两次 `recall`,**同一个 prompt**。第二次的同一卡应该
进 `skipped_already_recalled`,不进 `recalled`(在 dedup window 内)。

## 验证

- 第 1 次 recall:`round_count == 1`,`recalled` 含 card_X
- 第 2 次 recall:`round_count == 2`,`recalled` **不含** card_X(因为 round 1 在 window 内)
- `skipped_already_recalled` 含 card_X
