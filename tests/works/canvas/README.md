# works / canvas — 画布是视图:乐观锁与越界

## 这个场景在测什么
从未写过 = version 0 空画布;`PUT` 全量覆盖,`version` 必须等于当前否则 409;成功后 +1;块越出 24×16 → 409。
画布不建、不删会话(它只是 work 的显示层)。

## 不在这测什么
- 会话的建立 → `work_servers/`

## fixture 来源
`client`。
