# works / recall — 开工注入 card 目录

## 这个场景在测什么
`GET /api/works/{id}/recall` 是 card → work 的接口:把 collections 里 card 层的目录渲染成文本(`data` 是那段字符串);
`layer=` 可换层,`dir=` 只给某目录之下。

## 不在这测什么
- 目录怎么算 → `collections/tree_and_search`

## fixture 来源
`client`。
