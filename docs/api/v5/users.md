# Users API

user 是顶层对象:**不注册、不做权限**,在系统里出现过的名字就是 user。从 work(`created_by` / users 名单)和 collections(commit author)汇总;没有建 / 改 / 删,身份来自请求头 `X-Memory-Talk-User`。机制见 [designs user.md](../../designs/v5/user.md)。

## GET /api/users

所有出现过的 user,按 `last_seen` 倒序。

```json
[{"name": "alice", "works_created": 3, "works_touched": 5, "commits": 12, "active_works": ["work_…2f2f"], "last_seen": "2026-09-11T08:12:40Z"},
 {"name": "bob",   "works_created": 0, "works_touched": 2, "commits": 4,  "active_works": [],             "last_seen": "…"}]
```

| 字段 | 说明 |
|---|---|
| `works_created` / `works_touched` | 建了几个 / 动过几个 work |
| `commits` | collections 里以它为 author 的提交数(stack 的 first-parent,即每次层提交) |
| `active_works` | 最近 120 秒内动过的 work(和 work 的 users `current` 同一口径) |
| `last_seen` | 三处里最近的一次 |

服务配置的默认 author(`MEMORY_TALK_AUTHOR`,匿名提交)不算 user。

## GET /api/users/{name}

`User` + `works_created_ids` / `works_touched_ids` / `recent_commits`(最近 20 条,`{sha, date, subject}`)。不存在 → 404 `not_found`。

## GET /api/users/me

`X-Memory-Talk-User` 对应的 user 档案;没带头 → `null`;名字还没出现过 → 一份空白档案(只有 `name`),表示「存在,但还没做过任何事」。
