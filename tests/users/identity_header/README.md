# users / identity_header — 身份自报、必须注册、不做权限

## 这个场景在测什么
`X-Memory-Talk-User` 只查「注册过没有」:没注册的名字 → 404;不带头 = 匿名,照样能操作(不做权限);
`GET /api/users/me` 按头取档案,没带头给 null。

## 不在这测什么
- 身份进 work 的哪些地方 → `work_ownership`、`activity`
- 身份进 commit author → `commit_author`

## fixture 来源
`client`、`H`。
