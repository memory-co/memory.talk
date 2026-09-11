# collections / decide_and_discuss — 跨层的决定是两个相邻提交

## 这个场景在测什么
`decide`:issue 记 `card` + 新建卡(卡的 `issue` 指回),两个相邻提交各在自己的层、同一个 `Decision:` trailer;
`discuss`:对卡开讨论页,`[issue] raise` + `[card] link`,同一个 `Discussion:` trailer;卡已存在 → 409。

## fixture 来源
`client`、`H`、`_util.git_log`。
