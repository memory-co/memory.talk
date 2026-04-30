# test_recall_session_not_required

`recall` 不要求 `session_id` 在 v2 里存在,因为 hook 阶段 sync 还没跑。
传入一个完全没出现过的 `session_id`,recall 仍然成功(空命中是允许的)。

## 验证

- exit code 0
- session_id 被前缀化(`raw` → `sess_raw`)
- recall 表新增一行
- 即便 `recalled` 是空(corpus 里没相关卡),也不报错
