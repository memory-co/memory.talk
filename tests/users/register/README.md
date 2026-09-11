# users / register — user 是注册的实体

## 这个场景在测什么
`POST /api/users` 注册(name 唯一、格式受限、档案落盘)、`PUT` 改档案、`GET` 清单里注册了但没动过的人也在。
user 和 work 平级、有自己的存储——fs 下是 `users/<name>.json`,sqlite 下是 `users` 表;两种 store 各跑一遍。

## 不在这测什么
- 请求头里的身份校验 → `identity_header`
- 活动统计 → `activity`

## fixture 来源
`client`(已注册 alice / bob / carol)。
