---
name: explore
description: Use when importing conversation history from Claude Code, Codex, or other platforms
---

# Explore

发现并导入各平台的原始对话。一个命令搞定，自动去重。

## Steps

### 1. 同步所有平台

```
memory-talk sync
```

扫描所有已配置平台的默认目录（如 `~/.claude/projects/`），自动导入新会话、更新已变更会话。返回 JSON 汇总：

```json
{
  "platforms": [
    {"name": "claude", "sessions_total": 10, "sessions_new": 2, "sessions_updated": 1, "rounds_new": 87}
  ],
  "total": {"sessions": 10, "new": 2, "updated": 1, "rounds_new": 87}
}
```

已导入的 session 重复 sync 会被去重，可以随时跑。

### 2. 浏览并标记新 session

```
memory-talk session list                                    # 全部
memory-talk session list --tag claude --tag project:myapp   # 多 tag AND 筛选
```

### 3. 给新 session 打上 `unbuilt` tag

**tag 没有自动机制**，`built` / `unbuilt` 是 Agent 自己维护的工作流标签。sync 本身不打 tag，后续 `/build` 能不能用 `--tag unbuilt` 找到待整理 session，取决于这一步：

```
memory-talk session tag <session_id> add unbuilt
```

识别"哪些是新的 session"：`session tag <id> list` 返回空，或既没 `built` 也没 `unbuilt` 的，就是还没纳入工作流的。

### 4. 下一步

导入完成后提示用户走 `/build` 把 session 整理成 Talk-Card。
