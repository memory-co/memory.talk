# collections / config — collections.json:一份文件说清配置和层,git 历史是层的变化史

## 这个场景在测什么
仓库根的 `collections.json` 是被 git 追踪的锚定:始祖提交只有它;`layers[]` 最底在前,内置层标 `builtin`,用户层把 schema 内嵌进去并记 `added_at`;
`GET /api/collections/config` 给本体和它的提交历史(加层是最底层上的一次提交);仓库里没有别的机制文件(没有 `layers`、没有 `schemas/`),
`collections.json` 不出现在 tree / 目录 / 投递里。

## 不在这测什么
- 用户层的 schema 语义 → `user_layer`

## fixture 来源
`client`、`svc`、`H`。
