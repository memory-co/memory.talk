# Users API

user 是**注册的**顶层对象:有自己的存储(fs `users/<name>.json` / db `users` 表,走 provider)和档案。身份来自登录态(token,见 [auth.md](auth.md));权限只有一档:`admin` 管账号,其余谁都能动。机制见 [designs user.md](../../designs/v5/user.md)、[designs auth.md](../../designs/v5/auth.md)。

## POST /api/users

建账号(**admin**;member → 403 `forbidden`)。

```json
{"name": "alice", "display_name": "Alice", "email": "alice@example.com", "password": "至少 6 位"}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | 是 | 唯一 id,`[A-Za-z0-9_.-]{1,64}`;请求头和 commit author 用它 |
| `display_name` | 否 | |
| `email` | 否 | commit author 的邮箱;空则 `<name>@memory.talk` |
| `password` | 否 | 初始密码;空 = 先不能登录,之后 admin 用 `PUT /api/users/{name}/password` 设 |

**201** 返回 User(`name` / `display_name` / `email` / `created_at` / `role`)。`role` 是 `admin`(只有 `admin` 这个名字)或 `member`。密码哈希存在记录里,任何接口都不返回。已存在 → 409 `exists`;名字不合法 → 422。

## GET /api/users

所有注册的 user,档案 + 派生的活动统计,按 `last_seen` 倒序。

```json
[{"name": "alice", "display_name": "Alice", "email": "alice@example.com", "created_at": "…",
  "works_created": 3, "works_touched": 5, "commits": 12, "active_works": ["work_…2f2f"], "last_seen": "2026-09-11T08:12:40Z"},
 {"name": "carol", "display_name": "", "email": "", "created_at": "…",
  "works_created": 0, "works_touched": 0, "commits": 0, "active_works": [], "last_seen": ""}]
```

| 派生字段 | 说明 |
|---|---|
| `works_created` / `works_touched` | 建了几个 / 动过几个 work |
| `commits` | collections 里以它为 author 的提交数(stack 的 first-parent) |
| `active_works` | 最近 120 秒内动过的 work(和 work 的 users `current` 同一口径) |
| `last_seen` | 三处里最近的一次;从没动过 → 空 |

统计不落盘,读时从 work 和 collections 现算。

## GET /api/users/{name}

档案 + 统计 + `works_created_ids` / `works_touched_ids` / `recent_commits`(最近 20 条,`{sha, date, subject}`)。不存在 → 404。

## PUT /api/users/{name}

`{"display_name": "…", "email": "…"}`,都可选。自己的,或 admin 改谁的都行(否则 403)。返回 User。

## PUT /api/users/{name}/password

`{"old_password": "…", "new_password": "至少 6 位"}`。改自己的要带 `old_password`(不对 → 401);admin 给别人设不用带;member 改别人 → 403。改完这个人的 token 全部作废,要重新登录。返回 `{}`。

## GET /api/users/me

token 对应的档案(`UserProfile`);没登录 → 401。

没有 DELETE:名字已写进 work 的 `created_by` 和 collections 的历史,删了引用就悬空。
