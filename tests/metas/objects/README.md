# metas / objects — 对象的 CRUD:一个带后缀的目录,里面一组「字段 + 正文」的文件

## 这个场景在测什么
写 / 读 / 改 / 删三层对象:issue 是 `<path>.issue/`(`readme.md` + `positions/*.md`),card 是 `<path>.card/readme.md`,每个文件是 frontmatter 字段 + 正文,标题都是目录名;
origin 是不带后缀的文件;同一个主题文件夹里三者并排。写入口只有一个:`files`(目录里的文件),整批按层的协议校验,不过 → 422 且把理由带回来;
已存在 → 409、不存在 → 404;`edit` 只动提到的文件(`null` 删);`subject` 可自定提交主题;删了就没了(历史在 git,见 `history`)。

## 不在这测什么
- 协议的每条规则 → `protocol_rules`

## fixture 来源
`client`、`svc`。
