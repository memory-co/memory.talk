# users / commit_author — collections 的提交以 user 为 author

## 这个场景在测什么
带身份的 collections 写动作,git commit 的 author 是那个 user:名字 + 档案里的邮箱(没填则 `<name>@memory.talk`);
没填邮箱的用 `<name>@memory.talk`;`GET /api/users/{name}` 的 `commits` 和 `recent_commits` 从 git 汇总。

## 不在这测什么
- 提交本身的层语义 → `collections/`

## fixture 来源
`client`、`H`、`_util.git_authors`。
