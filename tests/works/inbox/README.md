# works / inbox — work 自己的变动沿树投递

## 这个场景在测什么
子 work 的创建 / 状态变化默认打到父的收件箱(`routed_by: parent`);`PUT /manager` 改写默认(存在 `works.manager` 列,`routed_by: <work_id>`),
`null` 回到父;根没有 manager、收件箱是空的。收件箱是 `works.db` 的 `inbox` 表,按先后读(旧的在前,`[-1]` 是最新的);改目标不投递。

## 不在这测什么
- metas 变动的投递 → `metas/inbox_delivery`
- work 自己的经过(段 / 点)→ `works/trace`

## fixture 来源
`client`。
