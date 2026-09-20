# metas / history — 改了留版本,git 就是历史

## 这个场景在测什么
`GET /api/metas/history/{layer}/{path}` 是那一层分支上关于这个对象的 log(新在前,subject 是 `[层] 动词 路径`,
body 里有 `Reason:`);`GET …?rev=<sha>` 读旧版本;删掉之后历史仍在。

## fixture 来源
`client`。
