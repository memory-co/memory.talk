# tag

给某个 session 加 / 去 tag。v2 里 tag 是一级命令,**只作用于 session**——`<session_id>` 必须以 `sess_` 开头。

## tag add

```bash
memory-talk tag add <session_id> <tag> [<tag> ...] [--json]
```

例:

```bash
memory-talk tag add sess_187c6576 decision project:memory-talk
```

- `<session_id>` 必须是 `sess_<...>`。前缀不对或 session 不存在返回错误。
- tag 已存在则不重复添加,幂等(log 里也不记重复事件)。

### Markdown(默认)

````markdown
ok: tags = `decision`, `project:memory-talk`
````

### JSON(`--json`)

```json
{"status": "ok", "tags": ["decision", "project:memory-talk"]}
```

返回的 `tags` 是本次操作之后该 session 上的**全部 tag**,不是增量。

## tag remove

```bash
memory-talk tag remove <session_id> <tag> [<tag> ...] [--json]
```

- `<session_id>` 必须是 `sess_<...>`。
- 要移除的 tag 不存在时静默跳过,幂等(log 里也不记)。

### Markdown

````markdown
ok: tags = `project:memory-talk`
````

全 tag 被清空时:

````markdown
ok: tags = *(empty)*
````

### JSON

```json
{"status": "ok", "tags": ["project:memory-talk"]}
```

同样返回移除后的全量 tag。

## 错误

| 情况 | 说明 |
|------|------|
| `<session_id>` 不以 `sess_` 开头(例如误传 `card_*`) | 400,`type mismatch: tag only applies to sessions` |
| session 不存在 | 404,`not found` |
| `tags` 参数为空 | Click 阶段就拦截,提示 `Missing argument 'TAGS...'` |

错误展示:

````markdown
**error:** type mismatch: tag only applies to sessions
````

`--json`:

```json
{"error": "type mismatch: tag only applies to sessions"}
```
