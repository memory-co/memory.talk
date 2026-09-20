# metas / recent — 最近改过的对象,像 git log 一样往下翻

## 这个场景在测什么
`GET /api/metas/recent`:沿 `stack` 的 first-parent 时间线往回走,每次提交碰的文件折回对象,每个对象只出现一次(落在它最近那次提交上,带那次动了哪些文件);
新的在前;`layer=` / `path=` 过滤;`limit=` + `before=<游标>` 翻页,`next` 是下一页游标,到底了是 `null`,去重跨页有效(一个对象翻到后面不会再出现);机制文件(`metas.json` / `manager.json`)不算。

## fixture 来源
`client`。
