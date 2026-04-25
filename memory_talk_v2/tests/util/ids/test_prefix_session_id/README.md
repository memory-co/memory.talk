# test_prefix_session_id

`prefix_session_id()` 把平台原生 session id(claude-code 是 ULID-like 字符串)
统一加上 `sess_` 前缀,且对已加前缀的输入是幂等的。

## 场景矩阵

| 测试函数 | 输入 | 预期 |
|---|---|---|
| `test_prefix_session_id_adds_prefix` | `"187c6576-875f"` | 输出以 `sess_` 开头 |
| `test_prefix_session_id_is_idempotent` | `"sess_187c6576-875f"` | 原样返回(不会变成 `sess_sess_...`)|

## 覆盖的代码路径

- `util/ids.py::prefix_session_id()`:存在前缀就直传,否则拼接

## 为什么需要幂等

claude-code adapter 在多处会传入同一个 session id —— 第一次入库时是裸字符串,
后续操作(查、改、关联)拿到的是已经带前缀的版本。如果幂等性破了,会出现
`sess_sess_...` 这种二次包裹,数据库索引立刻撕裂。
