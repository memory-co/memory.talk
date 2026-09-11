# collections / user_layer — 一份 YAML schema 就是一层

## 这个场景在测什么
`POST /api/collections/layers` 加用户层:schema 落在最底层的 `schemas/<名>.yaml`,新分支从始祖出发,排在内置层之上;
用户层没有行为;对象按 schema 校验(必填、`"list[string]"`、`ref`);重启后层还在。

## fixture 来源
`client`、`_util.git_log`。
