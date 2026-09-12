# collections / issue_rules — issue 目录的校验器:只增不改,边和排序有约束

## 这个场景在测什么
`layers/issue.py` 就是一个 `check(diff, after)`;这里把每条规则各碰一次,确认拒的时候理由带回来:
清单外的文件拒;`readme.md` 不能删;`positions/<主张>.md` 新建随意、改只能在末尾追加、不能删(改名 = 删 + 建,所以也不行);
`meta.yaml` 按 schema(`links[].type` 五种、`(type, target)` 不重复、`positions[].claim` 必须是已有立场、多余键拒);
一次提交里多个文件一起进 check,一个不过整批不落。谁、何时在 git。

## 不在这测什么
- 通用 CRUD / 409 / 404 → `objects`

## fixture 来源
`client`、`svc`、`_util.git_authors`。
