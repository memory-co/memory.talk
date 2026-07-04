# CLI (v5)

v5 的命令面。**读收敛成一个 `query`**(自由 SQL,[表结构即 API](../../structure/v5/README.md));写是一组受治理的 `card` 动作;经验摄入不在这(归独立的 [sync-server](../../works/v5/sync-server.md) 自己的控制面)。

```
memory.talk
├── query "<SQL>" [--as-of <ISO>] [--schema] [--json]     # 唯一读面 → query.md
├── card                                                   # mind 写动作 → card.md
│   ├── create --issue '<问题>' [--proof <type>:<ref>:<indexes> ...]
│   ├── position --card <cid> --claim '<答案>' --proof ...
│   ├── review --target <card#p|l n> --argument <+1|0|-1> --proof ... [--comment]
│   ├── link --card <cid> --type <t> --target <id> --claim '<为什么>' [--proof ...]
│   └── delete <card_id> [--yes] [--json]                 # 墓碑级联,先预览后确认
├── server  start | stop | restart | status               # memory daemon(形态沿 v4)
└── setup                                                  # 初始化(形态沿 v4)
```

## 跟 v4 命令面的对应

| v4 | v5 |
|---|---|
| `read` / `search` / `recall` / `card list` / `session list` … | **都进 `query`**(一条 SQL / 一份预制 SQL)。常用问法后续以 **sugar 子命令**回归(如 `recall`,= 预制 SQL + 渲染,能力层文档定型后补) |
| `session mark`(交互标注) | **不预制**(mark 载体由 harness 自己长,[mind-data](../../works/v5/mind-data.md)) |
| `sync` | 剥离为 **sync-server** 独立服务(自带 `sync-server status` 等控制面,契约见其 works 篇) |
| `card create/position/review/link/delete` | 保留,证据参数统一 `--proof <type>:<ref>:<indexes>`([card.md](card.md)) |

## 纪律

- CLI 是 [API](../../api/v5/README.md) 的薄壳:query → `POST /v5/query`,card → 写动作端点;不在 CLI 层藏逻辑;
- `--json` 全命令可用(AI 主消费者);markdown 是人读的默认渲染;
- 嵌入契约(CC 宿主怎么用这套命令)另篇(works 待写)。
