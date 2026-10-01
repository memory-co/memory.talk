# works / tree — work 树:建节点、父子、森林

## 这个场景在测什么
`POST /api/works` 建节点(可挂父),`GET /api/works` 返回森林(`children[]` 读时拼出来),`root=` 只看一棵;
父不存在 → 404;work 没有 project 字段;work 只存在 `<home>/works.db` 和 `<home>/worktrace.db` 两个 sqlite 里(没有 `works/` 目录树,
不随 `MEMORY_TALK_STORE` 变),路径可以用 `MEMORY_TALK_WORKS_DB` / `MEMORY_TALK_WORKTRACE_DB` 挪走。

## 不在这测什么
- 状态(运行中 / 归档)→ `status`
- 归属 → `users/work_ownership`

## fixture 来源
`client`。
