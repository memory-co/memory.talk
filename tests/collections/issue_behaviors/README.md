# collections / issue_behaviors — 立场、论证、边、排序

## 这个场景在测什么
issue 层校验器之上的四个快捷行为,以及它们各自碰哪个文件:`position` 新建 `positions/<主张>.md`(文件名就是主张,重复 → 409);
`argue` 往那个文件的 `## 论证` 下追加一行(立场不存在 → 404);`link` 往 `meta.yaml` 的 `links` 追加且不重复;
`rank` 整体替换 `meta.yaml` 的 `positions` / `summary`,读视图按它排序,没排到的按文件名;`rank` 指到不存在的立场 → 422。
谁、何时不在文件里,在 git;层没有的行为 → 404 `no_action`。

## 不在这测什么
- 直接用 `files` 往目录里放文件 → `objects`
- 对卡开讨论页(card 的行为)→ `discuss`

## fixture 来源
`client`、`svc`、`_util.git_log`。
