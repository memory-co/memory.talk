# CLI (v5)

v5 的命令面——**跟 v4 完全不同的结构,只有三个命令**:

```
memory.talk
├── query   [<SQL>]                # 问:唯一读面;不带 SQL 进交互模式(类 mysql CLI)→ query.md
├── sync    <status|…>             # 看/管:sync-server 的状态与操作 → sync.md
└── harness <start|stop|status|chat>   # 养:启动 CC 或 Lua 引擎跑 memory harness;
                                        #    harness 是个常驻 server,可对话 → harness.md
```

## 为什么只有这三个

人对一套记忆的合法动作就三种:**问它**(query)、**看经验进没进来**(sync)、**跟养它的管家说话**(harness)。

- **没有 `card` 等写命令**:写 mind 是 **harness 经受治理写动作([API](../../api/v5/cards.md))干的活**,不是人的手工活。人想影响记忆(「这条不对」「多关注 X」),**对话告诉 harness**(`harness chat`),让它去落——而不是绕过管家直接改库。
- **没有 `read` / `search` / `recall` / `list`**:全是 [query](query.md) 上的一条 SQL([表结构即 API](../../structure/v5/README.md))。
- **没有 `session mark`**:mark 载体不预制([mind-data](../../works/v5/mind-data.md)),harness 自己长。
- **没有 `server` 命令**:memory daemon 的生命周期收进使用它的命令(query / harness 按需拉起、`harness status` 里带 daemon 健康);sync-server 的生命周期在 `sync` 下。**人面对的是三件事,不是五个进程。**

## 纪律

- CLI 是薄壳:query → [`POST /v5/query`](../../api/v5/query.md);sync → sync-server 控制面;harness → harness server 控制面 + 对话通道;
- `--json` 全命令可用(AI / 脚本消费);默认输出是人读的 markdown / 表格;
- 嵌入契约(CC **宿主**场景怎么用 query——区别于 harness 的 CC **引擎**)另篇(works 待写)。
