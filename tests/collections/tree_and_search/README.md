# collections / tree_and_search — 目录、grep

## 这个场景在测什么
`GET /api/collections/{layer}` 按目录树列标题(`dir=` 只看一段;issue 的标题是目录名);
`GET /api/collections/tree` 把带后缀的目录折成一项;`GET /api/collections/search` 是 `git grep`,可按层过滤,一行一条,命中 issue 目录里任何文件都归到那个 issue。
没有向量库、没有索引。

## fixture 来源
`client`。
