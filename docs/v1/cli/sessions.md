# sessions

管理已导入的 session。

## sessions list

列出 session，可筛选未整理的。

```bash
memory-talk sessions list [--unbuilt]
```

## sessions read

读出 session 的所有 rounds。

```bash
memory-talk sessions read <SESSION_ID>
```

输出：Round 对象的 JSON 数组，每个 Round 包含 `round_id`、`speaker`、`role`、`content`（ContentBlock 列表）。

## sessions mark-built

标记 session 已被 Build 整理完毕。

```bash
memory-talk sessions mark-built <SESSION_ID>
```
