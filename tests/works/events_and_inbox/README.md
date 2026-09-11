# works / events_and_inbox — work 的时间线,以及沿树投递

## 这个场景在测什么
`events.jsonl` 的顺序(created → status → frozen);子 work 的创建 / 状态变化默认打到父的收件箱(`routed_by: parent`);
`works/<id>/manager.json` 改写默认(`routed_by: <work_id>`),`null` 回到父;根没有 manager。

## 不在这测什么
- collections 变动的投递 → `collections/inbox_delivery`

## fixture 来源
`client`。
