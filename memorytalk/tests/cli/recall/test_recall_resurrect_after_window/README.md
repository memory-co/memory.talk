# test_recall_resurrect_after_window

测试滑动窗口的复活逻辑:`settings.recall.dedup_window_rounds` 默认 5。
跑超过 5 轮的同一 session,第 1 轮的卡应该在第 7+ 轮可以再次召回。

## 做法

1. 把 `settings.recall.dedup_window_rounds` 设小一点(2),减少跑轮数
2. round 1:recall 卡 X
3. round 2:recall 不同的 prompt(但仍命中卡 X 时它进 skipped)
4. round 3:recall 同一个 prompt → 卡 X 已经超出 window(round 1 < 3 - 2),应该重新出现在 `recalled`

## 验证

- round 3 的 `recalled` 含卡 X(复活)
- `skipped_already_recalled` 不含 X(它已经超出 window 了)
