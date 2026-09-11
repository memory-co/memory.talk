# collections / issue_behaviors — 立场、论证、边、派活

## 这个场景在测什么
issue 层 schema 之上的行为:`position` 只增(id 顺序编号)、`argue` 带方向与证据、读视图现算 up / down / neutral / credence 并按 credence 倒序、
`link` 连 IBIS 边且不重复、`spawn` 记派出的 work;立场不存在 → 404,层没有的行为 → 404 `no_action`。

## 不在这测什么
- 写卡 / 开讨论页(跨层)→ `decide_and_discuss`

## fixture 来源
`client`。
