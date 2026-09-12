# collections / layers — 三个内置 layer 及它们的目录规则

## 这个场景在测什么
`GET /api/collections/layers`:origin / issue / card 的顺序(最底在前)、后缀(origin 没有)、每层允许的文件清单(格式 / 必需)、标题来源、行为清单;
仓库初始化后就有三条 `layer/*` 分支和 `stack`。

## 不在这测什么
- 用户层 → `user_layer`

## fixture 来源
`client`、`svc`。
