# collections / objects — 对象的 CRUD:一个带后缀的目录,里面一组文件

## 这个场景在测什么
写 / 读 / 改 / 删三层对象:issue 是 `<path>.issue/` 目录(`readme.md` + `meta.yaml` + `positions/*.md`,标题 = 目录名),
card 是 `<path>.card/card.md`(frontmatter + 正文,`data` 简写按字段写),origin 是不带后缀的文件;同一个主题文件夹里三者并排;
写入口是 `files`(目录里的文件),整目录按层的 schema 校验:清单外的文件、缺必填 → 422;已存在 → 409、不存在 → 404;
`edit` 只动提到的文件(`null` 删),`data` 合并字段;删了就没了(历史在 git,见 `history`)。

## fixture 来源
`client`、`svc`。
