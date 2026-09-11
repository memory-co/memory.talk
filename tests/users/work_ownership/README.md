# users / work_ownership — work 有归属:created_by

## 这个场景在测什么
建 work 时请求头里的 user 写进 `created_by`,建后不改;`GET /api/works?created_by=` 按人筛;
子 work 不继承父的归属;建者自动进 users 名单第一个。

## 不在这测什么
- 谁在动 / 动过(users 名单的窗口语义)→ `activity`

## fixture 来源
`client`、`H`。
