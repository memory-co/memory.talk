# CLI (v5)

v5 的命令面——**跟 v4 完全不同的结构,只有三个顶层命令**:

```
memory.talk
├── reality [<SQL>]                # 问经验库(共享一份;单发/交互 REPL)→ reality.md
├── sync    <status|…>             # 看/管:sync-server 的状态与操作 → sync.md
└── agent                          # 实例化的记忆管家 → agent.md
    ├── create <name> --harness claude-code|codex|quickjs
    ├── list · start · stop · status
    ├── chat <name> [<msg>]        #   跟某个实例对话(人影响记忆的正门)
    └── mind <name> [<SQL>]        #   查该实例的 mind 库(每实例一个独立库)
```

## 为什么长这样

人对记忆的合法动作就三种:**问**(reality 共享经验;`agent mind <name>` 问某个实例的信念)、**看**(sync:经验进没进来)、**说**(agent chat:跟管家对话)。

- **没有全局 `mind` 命令**:mind 库**每个 agent 实例一个**(信念有主人),问信念必须点名——`agent mind curator "…"`;reality 只有一份共享,所以它是顶层命令。
- **没有 `card` 等写命令**:写 mind 是**该 agent 经受治理写动作([API](../../api/v5/cards.md))干的活**。人想影响记忆,`agent chat` 说给它听——不绕过管家直接改库。
- **没有 `read` / `search` / `recall` / `list`**:全是一条 SQL([表结构即 API](../../structure/v5/README.md))。
- **没有 `server` 命令**:daemon 生命周期收进用它的命令;sync-server 归 `sync`,实例 server 归 `agent start/stop`。

## 纪律

- CLI 是薄壳:reality → [`POST /v5/query`](../../api/v5/query.md);agent → [实例 API](../../api/v5/agent.md)(registry / chat / status / mind query);sync → sync-server 控制面;
- `--json` 全命令可用(AI / 脚本消费);默认输出是人读的 markdown / 表格;
- 嵌入契约(CC **宿主**怎么嵌:hooks 无意识召回 / skills 有意识检索 + chat 转发 / CLAUDE.md 行为指引)→ [works/v5/embed-contract.md](../../works/v5/embed-contract.md)。
