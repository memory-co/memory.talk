# collections / discuss — 对卡开讨论页:卡记 issue,issue 不记卡

## 这个场景在测什么
card 的 `discuss`:新建一个 issue(`[issue] write`)+ 卡的 `issue` 字段指过去(`[card] link`),两个提交各在自己的层,没有 trailer;
issue 那边什么都不记;issue 已存在 → 409。争出结果写卡就是普通的 card create,`issue` 字段自己填。

## fixture 来源
`client`、`_util.git_log`。
