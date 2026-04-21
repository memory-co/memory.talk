# tag

给 search 结果里的某个 session 加 / 去 tag。v2 里 tag 是一级命令，**只作用于 session**——传入 card 类型的 result_id 会返回 type mismatch。

## tag add

```bash
memory-talk tag add <result_id> <tag> [<tag> ...]
```

例：

```bash
memory-talk tag add sch_01K7XABC....s1 decision project:memory-talk
```

- `<result_id>` 必须是 session 类型（`.s<N>`）。
- tag 已存在则不重复添加，幂等。
- 过期 / 未知 result_id 返回错误，tag 不被应用。

输出：

```json
{"status": "ok", "tags": ["decision", "project:memory-talk"]}
```

返回的 `tags` 是本次操作之后该 session 上的**全部 tag**，不是本次新增的增量。

## tag remove

```bash
memory-talk tag remove <result_id> <tag> [<tag> ...]
```

- `<result_id>` 必须是 session 类型。
- 要移除的 tag 不存在时静默跳过，幂等。

输出：

```json
{"status": "ok", "tags": ["project:memory-talk"]}
```

同样返回移除后的全量 tag。
