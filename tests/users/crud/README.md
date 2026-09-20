# users / crud — user 的增、查、改,以及为什么没有删

## 这个场景在测什么
user 是注册的实体、和 work 平级、有自己的存储。本场景把 `/api/users` 的每个动作走一遍,两种 store(fs / sqlite)各跑一次:

| | 端点 | 测什么 |
|---|---|---|
| **C** | `POST /api/users` | 全字段注册;缺省字段的默认值;`created_at` 是 UTC 时间;`name` 唯一(409);`name` 格式(422:空格、中文、超长);档案真的落在仓储里 |
| **R** | `GET /api/users/{name}` | 档案字段原样;不存在 404;刚注册的人统计全是 0 / 空 |
| **R** | `GET /api/users` | 所有注册的人都在(没动过的也在);带派生统计;排序按最近活动、没动过的按名字 |
| **R** | `GET /api/users/me` | 按请求头取;没带头 → null;头里的名字没注册 → 404 |
| **U** | `PUT /api/users/{name}` | 改 display_name / email;只传一个字段另一个不动;传空字符串就是清空;`name` 和 `created_at` 改不了;不存在 404;改完读回一致、清单里也变了 |
| **D** | `DELETE /api/users/{name}` | **没有这个端点**(405):名字已写进 work 的 created_by 和 metas 的历史,删了引用就悬空——这是设计约定([designs user.md §7](../../../docs/designs/v5/user.md)) |

## 不在这测什么
- 请求头里的身份怎么用 → `identity_header`
- 归属、活动统计、commit author → `work_ownership` / `activity` / `commit_author`

## fixture 来源
`client`(已注册 alice / bob / carol)、`svc`。
