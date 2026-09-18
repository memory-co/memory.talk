# collections / layers — 三个内置 layer:每层就是一份协议

## 这个场景在测什么
`GET /api/collections/layers`:origin / issue / card 的顺序(最底在前)、后缀(origin 没有)、每层的 `protocol`(object 规则:目录名正则 / name / under;files:每种文件的 pattern / example / fixed / required / format.fields / body / template);
仓库初始化后就有三条 `layer/*` 分支和 `stack`。

## 不在这测什么
- 协议怎么校验写入 → `protocol_rules`;tree 的「能建什么」→ `tree_can_create`;用户层 → `user_layer`

## fixture 来源
`client`、`svc`。
