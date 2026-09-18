# collections / tree_and_search — 目录、grep

## 这个场景在测什么
`GET /api/collections/tree` 一个接口管浏览:`layer=` 只留一层(目录保留,能继续往下走),`recursive=1` 往下走到底、拍平列对象(标题就是目录名);
`GET /api/collections/tree` 把带后缀的目录折成一项;`GET /api/collections/search` 是 `git grep`,可按层过滤,一行一条,命中 issue 目录里任何文件都归到那个 issue。
没有向量库、没有索引。

## fixture 来源
`client`。
