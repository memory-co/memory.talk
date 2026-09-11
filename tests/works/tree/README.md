# works / tree — work 树:建节点、父子、森林

## 这个场景在测什么
`POST /api/works` 建节点(可挂父),`GET /api/works` 返回森林(`children[]` 读时拼出来),`root=` 只看一棵;
父不存在 → 404;work 没有 project 字段。

## 不在这测什么
- 状态与完成收拢 → `status`
- 归属 → `users/work_ownership`

## fixture 来源
`client`。
