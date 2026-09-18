# search — 一个入口,各家各出一份

## 这个场景在测什么
`GET /api/search?q=`:SearchService 把同一个 q 交给 work / collections / users 三个 service 的 `search()`,汇总成 `{query, hits, counts}`;
work 按目标匹配(新的在前,带状态),collection 是 git grep 全文(命中折回对象,带层 / 文件 / 行号,机制文件不算),user 按名字 / 显示名 / 邮箱;
`limit` 是每种各最多几条,`counts` 是截断前各命中几条;空 q → 422。

## fixture 来源
`client`、`H`。
