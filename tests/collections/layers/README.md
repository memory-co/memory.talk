# collections / layers — 三个内置 layer:每层就是一个校验器

## 这个场景在测什么
`GET /api/collections/layers`:origin / issue / card 的顺序(最底在前)、后缀(origin 没有)、每层允许的文件清单;内置层没有 schema(规则在代码里);
仓库初始化后就有三条 `layer/*` 分支和 `stack`。

## 不在这测什么
- 各层的规则本身 → `issue_rules` / `objects`;用户层 → `user_layer`

## fixture 来源
`client`、`svc`。
