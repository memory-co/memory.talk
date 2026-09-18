# collections / config — collections.json:一份文件说清配置和层,git 历史是层的变化史

## 这个场景在测什么
仓库根的 `collections.json` 是被 git 追踪的锚定:始祖提交只有它;`layers[]` 最底在前,只有名字和 `builtin`;`<home>/layers/` 里多了一份 .yaml,启动时补进去,是最底层上的一次提交;
`GET /api/collections/config` 给本体和它的提交历史;仓库里没有别的机制文件(没有 `layers`、没有 `schemas/`),
`collections.json` 不出现在 tree / 目录 / 投递里。

## 不在这测什么
- 用户层的 check 本身 → `user_layer`

## fixture 来源
`client`、`svc`、`H`。
