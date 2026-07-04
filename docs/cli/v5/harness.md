# harness — 启动引擎、跟管家对话(v5 CLI)

[memory harness](../../works/v5/memory-harness.md) 的控制面:**选一个引擎(CC / Lua)把 harness 跑起来;它是个常驻 server,人可以跟它对话**。

```bash
memory.talk harness start [--engine cc|lua]   # 起 harness server(引擎二选一;默认 cc)
memory.talk harness stop                       # 停
memory.talk harness status [--json]            # 引擎/在忙什么/预算;顺带 memory daemon 健康
memory.talk harness chat [<一句话>]            # 对话:带话=单发,不带=进对话
```

## start — 引擎二选一,同一能力面

| | `--engine cc` | `--engine lua` |
|---|---|---|
| loop | 租 CC 的 agentic loop(专职实例,**剥掉 WebSearch / 文件读写 / Bash**) | 自研 Lua 循环,沙箱 VM |
| 能力面 | 只挂 memory interface(query + 受治理写动作) | 只注入 interface + `llm()` |
| harness session | 单一长会话 | 无 session |
| 自进化 | 否 | 是(engine_versions,影子对照 + 可回滚) |

起来之后它就是**一个常驻 server**:自己的 loop(摄入 → 提炼 → 治理 → 巩固)按触发跑,同时开着**对话通道**。

## chat — 人影响记忆的正门

```
$ memory.talk harness chat
harness (engine: cc, 治理中: 去重扫描 32/74)
you> card_01j… 那张卡的最优答案过时了,新结论在昨天那个 session 里
harness> 收到。我读了 sess_9f2…:38-52,给 card_01j… 加了新 position(#p3)
         并踩了 #p1(-1,引证 38-41)。credence 现在 p3 领先。
you> 最近为什么建了这么多 auth 相关的卡?
harness> 本周 12 张里 9 张来自 sess_8ab…(你在重构 auth)。其中 4 张 issue 相似度 >0.8,
         我准备今晚的巩固轮里合并成 2 张,可以吗?
```

- **对话是「跟管家说话」,不是「改库快捷键」**:你说的话是**给 harness 的输入**,落不落、怎么落由它经受治理写动作决定(它会告诉你它做了什么、引证在哪);
- **这就是为什么 CLI 没有 `card` 写命令**:人绕过管家直接写库,corpus 的一致治理就破了——要影响记忆,说给它听;
- 单发形态给脚本 / hooks:`memory.talk harness chat "今天优先消化 sess_9f2…" --json`。

## status — 它在忙什么

```
harness: running (engine=cc, up 6h)   memory daemon: ok   outbox: 0 pending
当前: 巩固轮(聚类 cards 74 → 候选合并 3 组)
预算: 今日 token 41% 已用   最近动作: review×4, link×1, create_card×2 (2h)
```

## 边界与待定

- harness server 的**动作面永远只有 memory interface**(能力收窄是引擎无关的纪律,[memory-harness §2](../../works/v5/memory-harness.md));chat 不给它开新口子;
- 对话历史本身也是经验:harness 可把 chat 记录当 `(type, ref)` 证据源之一(待定,连着 mind-data 的 file 型问题);
- start 触发的引擎细节(CC headless 形态 / Lua VM 配额)、chat 的传输(本地 socket / HTTP)——[memory-harness §6 待定](../../works/v5/memory-harness.md)。
