# metas —— 元认知页

单位是**一个文件**,像 Notion 的一页:标题、属性行、正文。前端不认识具体哪一层,一切形状来自 `GET /metas/layers` 里的协议(`lib/protocol.ts`)。

| 文件 | 重点 |
|---|---|
| `Library.tsx` | `Library`:左边层 tab(全部 + 各层)+ 视图切换(最近修改 `RecentList` 用 `/recent`;文件目录 `TreeList` 用 `/tree`,`.issue/` 这种对象目录照常进去)+ 「新建…」下拉(选项来自当前目录 `tree.can_create`);右边 `FilePage`。选择分两件事:`filter` 是列表看哪层(只由 tab 改),`layer + path + file` 是打开的文件;`dir` 进 URL 给面包屑用。`FilePage`:浏览 / 编辑 / 新建同一页——标题(新建时是名字输入框)、属性(`Properties` 只读 / `FieldsForm` 编辑)、正文(Milkdown,只读同一个编辑器)、同对象里的其他文件;新建时按 `NewFile{layer, dir, object?, kind?}` 决定是 POST 新对象的主文件还是 PUT 对象里的一个文件,输入时 `?dry_run=1` 预校验。小工具:`fileTitle`(readme 用对象名,别的用正则里 name 那段)、`fullPath`、`objectOf` |
| `FieldsForm.tsx` | `FieldsForm` / `FieldInput`:按字段类型画控件(string / text / number / bool / date / enum / ref / list / list of object),值保持原样,保存时再 `normalize` |
