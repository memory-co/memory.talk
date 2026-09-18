# collections / tree — 目录浏览

## 这个场景在测什么
`GET /api/collections/tree` 一个接口管浏览:`layer=` 只留一层(目录保留,能继续往下走),`recursive=1` 往下走到底、拍平列对象(标题就是目录名);
`GET /api/collections/tree` 把带后缀的目录折成一项。检索在 `tests/search`。

## fixture 来源
`client`。
