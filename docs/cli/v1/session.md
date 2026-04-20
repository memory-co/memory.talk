# session

管理已导入的 session。

## session list

列出 session，支持按 tag 筛选。

```bash
memory-talk session list [--tag <TAG>]
```

| 选项 | 说明 |
|------|------|
| `--tag` | 按 tag 筛选，可多次使用（AND 关系） |

示例：
```bash
memory-talk session list --tag claude --tag project:myapp
```

## session read

读出 session 的所有 rounds，可指定范围。

```bash
memory-talk session read <SESSION_ID> [--start N] [--end M]
```

输出：Round 对象的 JSON 数组，每个 Round 包含 `round_id`、`speaker`、`role`、`content`（ContentBlock 列表）。

## session tag

管理 session 的 tag。

```bash
memory-talk session tag <SESSION_ID> add <TAG> [<TAG>...]
memory-talk session tag <SESSION_ID> remove <TAG> [<TAG>...]
memory-talk session tag <SESSION_ID> list
```

示例：
```bash
memory-talk session tag abc123 add claude project:myapp important
memory-talk session tag abc123 remove important
memory-talk session tag abc123 list
```

Tag 是自由文本，建议用 `key:value` 格式表达维度，例如：
- `claude` / `codex` — 来源平台
- `project:myapp` — 所属项目
- `topic:database` — 话题
- `important` — 重要标记
- `built` / `unbuilt` — 整理状态（系统自动维护）
