# collections / user_layer — 一份 YAML schema 就是一层

## 这个场景在测什么
`POST /api/collections/layers` 加用户层:schema 内嵌进 `collections.json`,新分支从始祖出发,排在内置层之上;用户层没有行为;
单文件简写(`format` + `fields`)→ 目录里只有 `<层>.md`,`data` 按字段写;`files` 清单写法 → 多文件目录,整目录校验;
必填、`"list[string]"`、`ref`、清单外文件 → 422;重启后层还在。

## fixture 来源
`client`、`_util.git_log`。
