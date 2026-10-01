# users / work_ownership — work 有归属:created_by

## 这个场景在测什么
建 work 时请求头里的 user 写进 `created_by`,建后不改;`GET /api/works?created_by=` 按人筛;
子 work 不继承父的归属;建者开了这个 work 的 `work` 段(轨迹里 `user.id` 是他),这会儿也在看它(`current`)。

## 不在这测什么
- 谁在看(心跳、离开、超时)→ `works/viewers`;派生的活动统计 → `activity`

## fixture 来源
`client`、`H`。
