# agent — 实例化的记忆管家(v5 CLI)

[agent](../../works/v5/agent.md) 的控制面:**建实例、选 harness 底座、跟每个实例对话、查每个实例的 mind**。命令是 [api/v5/agent.md](../../api/v5/agent.md) 的薄壳。

```bash
memory.talk agent create <name> --harness claude-code|codex|quickjs   # 建实例(+它的空 mind 库)
memory.talk agent list                                             # 所有实例:name/harness/状态
memory.talk agent start <name> | stop <name>                       # 实例的常驻 server 生命周期
memory.talk agent status [<name>] [--json]                         # 在忙什么/预算;不给 name = 全部
memory.talk agent chat <name> [<一句话>]                           # 对话:带话单发,不带进对话
memory.talk agent mind <name> [<SQL>]                              # 查该实例的 mind 库(单发/REPL)
```

## 实例化:一个 reality,多个 mind

每个 agent 有**自己独立的 mind 库**(信念各自长);[reality](reality.md) 全局一份共享(经验是客观事实)。所以**没有全局 `mind` 命令**——问信念必须点名问谁的:

```bash
memory.talk agent mind curator "SELECT card_id, issue FROM v_cards ORDER BY created_at DESC LIMIT 20"
memory.talk agent mind curator --ds-end 20260601 "SELECT * FROM v_card_best"   # 时光机(天粒度)
memory.talk agent mind curator          # REPL(形态同 reality 命令:多行+`;`、\d、\ds、\json)
```

两步取证照旧:`agent mind <name>` 查证据指针 `(type, ref, indexes)` → session 型去 [`reality`](reality.md) 查原文。

## chat — 人影响记忆的正门

```
$ memory.talk agent chat curator
curator (harness: claude-code, 治理中: 去重扫描 32/74)
you> card_01j… 那张卡的最优答案过时了,新结论在昨天那个 session 里
curator> 收到。我读了 sess_9f2…:38-52,加了 #p3 并踩了 #p1(-1)。credence 现在 p3 领先。
```

- 你说的话是**给该实例的输入**:落不落、怎么落由它经受治理写动作决定(响应 `actions` 列明做了什么、引证在哪),动作只写**它自己的 mind**;
- **对话本身落库**:每条消息(双向)进 reality 的 [`conversations` 表](../../structure/v5/reality.md)(带 `agent` 字段)——可回放、可语义搜;
- **这就是为什么没有 `card` 写命令**:人绕过管家直接写库,信念的一致治理就破了——要影响记忆,说给它听;
- 单发给脚本 / hooks:`memory.talk agent chat curator "今天优先消化 sess_9f2…" --json`。

## status — 它(们)在忙什么

```
$ memory.talk agent status
agent     harness      state          current                  budget   daemon
curator   claude-code  governing      去重扫描 32/74            41%      ok
sandbox   quickjs(v12) consolidating  聚类 74 → 候选合并 3 组    12%      ok
```

## harness 三选(建实例时定)

| `--harness` | 底座 | 自进化 |
|---|---|---|
| `claude-code` | 租 CC 的 loop,剥基础工具,单一长会话 | 否 |
| `codex` | 租 Codex 的 loop,同样剥工具 | 否 |
| `quickjs` | 自研 JS 循环:QuickJS 引擎跑在 WASM 沙箱,无会话 | **是**(影子对照 + 可回滚) |

换 harness 不换任何契约(chat / status / mind 全同)——细节见 [works/v5/agent.md §2](../../works/v5/agent.md)。
