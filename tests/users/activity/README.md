# users / activity — 谁在动、谁动过

## 这个场景在测什么
带身份的、会动 work 的请求记进它的 users 名单(建、改、打开 work 本身、心跳);`current` = 最近 120 秒内动过(现算),
`history` = 动过的所有人按最近活动倒序;进了门就有名字,每个操作都记到人;`GET /api/users` 上的派生统计(建了几个 / 动过几个 / 正在动哪些)。

## 不在这测什么
- 归属(created_by)→ `work_ownership`

## fixture 来源
`client`、`H`、`svc`(直接改仓储里的 last_seen 模拟时间流逝)。
