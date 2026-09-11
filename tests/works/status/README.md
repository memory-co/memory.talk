# works / status — 完成从叶子往上收拢

## 这个场景在测什么
`done` 要求所有子 work 都是 done / abandoned,否则 409 并列出未完的子;`done` / `abandoned` 写 `done_at`,回到 doing 清空;
结束后的 work 不能再 attach 会话(409)。

## 不在这测什么
- 结束时现场销毁 → `work_servers/freeze`

## fixture 来源
`client`。
