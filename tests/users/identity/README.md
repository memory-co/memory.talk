# users / identity — 身份来自登录态

## 这个场景在测什么
名字不再自报:`Authorization: Bearer <token>` 解析出谁在操作;没带、或 token 不认识 → 401 `unauthorized`,什么都做不了;
`GET /api/users/me` 就是 token 对应的档案。原来的 `X-Memory-Talk-User` 头被忽略。

## 不在这测什么
- setup / 登录 / 注销 / 改密码本身 → `auth/gate`
- 身份进 work 的哪些地方 → `work_ownership`、`activity`
- 身份进 commit author → `commit_author`

## fixture 来源
`client`、`H`。
