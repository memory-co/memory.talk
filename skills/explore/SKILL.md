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

### 2. 浏览导入结果

```
memory-talk session list                  # 全部
memory-talk session list --tag unbuilt    # 还没整理成 card 的
memory-talk session list --tag claude --tag project:myapp   # 多 tag AND 筛选
```

`built` / `unbuilt` 是系统自动维护的 tag：sync 后新 session 自动带 `unbuilt`，被 build 流程整理出 card 后自动变成 `built`。

### 3. 下一步

导入完成后提示用户走 `/build` 把 session 整理成 Talk-Card。
