# metas / protocol_rules — 引擎按协议逐条校验

## 这个场景在测什么
一份 YAML 协议(这里拿内置的 issue)在引擎里对应的每一条检查,各碰一次,确认拒的时候理由带回来:
路径必须整段匹配某一种文件;`required` 的不能缺、不能删;固定文件只能一个;frontmatter 只能有声明的字段、`required` 的字段要有、
按类型校验(enum 的 values、number、list 里的 object、ref 是文本);纯正文的文件不能写 frontmatter;
对象目录名要匹配 `object.pattern`、放在 `under` 允许的位置、不能嵌在别的对象里;一批改动一个不过整批不落;谁、何时在 git。

## 不在这测什么
- 通用 CRUD / 409 / 404 → `objects`;能建什么 → `tree_can_create`

## fixture 来源
`client`、`svc`、`_util.git_authors`。
