# metas / tree_can_create — tree 顺带回答「这里还能建什么」

## 这个场景在测什么
`GET /api/metas/tree?path=` 除了 `items`,还给 `can_create`:普通目录按每一层的 object 规则列能不能建对象(`under` 不匹配给理由),origin 文件总能放;
对象目录按这一层协议逐种文件回答(固定文件已存在 → 不能,带 name 的一类给 example 和 existing);对象里的子目录只列能落到这里的种类。
带 `candidate=` 时回答这个名字行不行:普通目录问对象目录名,对象目录问文件路径。

## fixture 来源
`client`。
