# collections / objects — 对象的 CRUD:带后缀的目录,放哪都行

## 这个场景在测什么
写 / 读 / 改 / 删三层对象:issue 是 `<path>.issue/issue.json`,card 是 `<path>.card/card.md`(frontmatter + 正文),
origin 是不带后缀的文件;同一个主题文件夹里三者并排;schema 校验(缺必填 → 422)、已存在 → 409、不存在 → 404;
`edit` 合并字段、`null` 不动;删了就没了(历史在 git,见 `history`)。

## fixture 来源
`client`。
