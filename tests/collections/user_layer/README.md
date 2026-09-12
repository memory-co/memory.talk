# collections / user_layer — 一份 YAML 清单就是一层

## 这个场景在测什么
`POST /api/collections/layers` 加用户层:schema 内嵌进 `collections.json`,新分支从始祖出发,排在内置层之上;`GET /layers` 原样给出它的 schema;
清单编译成 `check`:清单外文件拒、`required` 的不能缺 / 不能删、`append_only` 的只能追加、yaml / json 文件按 `fields` 校验(必填、`"list[string]"`、多余键拒);
重启后层还在。

## fixture 来源
`client`、`_util.git_log`。
