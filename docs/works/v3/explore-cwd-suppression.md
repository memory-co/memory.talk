# Explore cwd suppression

`memory.talk explore` 模式:在隔离 cwd 里跑 Claude Code 让它抽 card / 写 review,**期间不希望 recall hook 自动召回**打扰 LLM。这份文档讲整套机制怎么靠 cwd 一个物理信号串起来。

相关:
- CLI: [`../../cli/v3/explore.md`](../../cli/v3/explore.md)
- Recall hook 接到 cwd 的判定: [recall-pipeline.md](recall-pipeline.md)

## 三件事靠 cwd 串起来

1. **explore namespace 靠 cwd 物理隔离**
   所有 claude 进程都在 `<settings.explore.cwd>` 下起;这个目录下的 session 在 backend 里通过 `metadata.cwd` 字段被识别为"explore session"。**不**依赖 tag / 任何额外元数据 —— cwd 是 Claude Code 原生的 project 分桶机制,backend 只是消费它。

2. **explore namespace 是 recall hook 的真空区**
   `<explore.cwd>/.claude/settings.json` 显式覆盖 user-level recall hook,在这里跑的 claude 不会被自动召回打扰 —— 抽 card / 写 review 场景里 LLM 需要清醒决定"我要看什么",不需要"系统帮我想起来"。

3. **recall hook 自己也检查 cwd**
   recall 服务端在收到 hook 调用时,如果 `payload.cwd` 落在 `settings.explore.cwd` 前缀下,**直接跳过这次召回**(emit 空 `hookSpecificOutput`,不写 recall_event)。这是双保险 —— 即使 `<explore.cwd>/.claude/settings.json` 因任何原因没生效,服务端也会拦下。

## settings.json 形态

```json
{
  "explore": {
    "cwd": "~/.memory.talk/explore"
  }
}
```

| 字段 | 默认 | 说明 |
|---|---|---|
| `explore.cwd` | `~/.memory.talk/explore` | claude 启动目录。绝对路径或 `~/` 起头。backend 做 namespace 判断时按**完全展开后的绝对路径前缀**匹配 `session.metadata.cwd`。 |

## setup 的 explore 初始化

setup wizard 首次跑会:

1. `mkdir -p <explore.cwd>` —— 创建空目录
2. 在 `<explore.cwd>/.claude/settings.json` 写 hook 覆盖(`UserPromptSubmit: []`)
3. 摘要里报告"explore 目录已就绪"

已存在目录不动 —— setup 幂等。

## recall 服务端的 cwd 判定

recall hook payload 来自 Claude Code 的 UserPromptSubmit,带 `cwd` 字段:

```json
{
  "session_id": "187c6576-...",
  "prompt": "请抽这条 session 的 insight",
  "cwd": "/Users/zzz/.memory.talk/explore"
}
```

recall 服务:

```python
explore_cwd = settings.explore.cwd  # 展开后的绝对路径
caller_cwd = payload.get("cwd")
if caller_cwd and same_path(caller_cwd, explore_cwd):
    emit({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                  "additionalContext": ""}})
    return  # 不查后端,不写 recall_event
```

判定走 `same_path` —— `~/` 展开 + symlink resolve 都做。让用户能用 `~/.memory.talk/explore` 或 `/Users/zzz/.memory.talk/explore` 都能匹配上。

## explore 不持有独立工作队列

候选 session 直接从 backend 查("没被任何 card 引用过"是个 SQL 自然推得的集合);产出从 backend 反查("这条 session 上产出了几张 card / 几条 review")。**无 cursor、无 checkpoint、无 explore-side state file**。

```
pending = {
  session | NOT EXISTS(card.rounds[*].session_id = session.id)
        AND session.metadata.cwd NOT startswith <explore.cwd>
        AND session.last_at <= now - 30min
}
```

三条规则:

- **未被引用**:还没有任何 card 的 rounds 引用过这条 session
- **不是 explore 自己产出的**:排除 `<explore.cwd>` 下的 session(避免"抽 explore session 套娃")
- **最近一轮 ≥ 30 分钟前**:可能还在跑的 session 暂不进队列(`last_at` 在 30 分钟内的算"active",pending 不取)

所有这些都 derive 自 backend 的 sessions + cards 数据,explore CLI 只是查 backend 然后展示。
