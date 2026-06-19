# insight

**v3 那套卡改名而来**(一句 `insight` + rounds + 论坛 stats)。v4 把 `card` 这个名字腾给问答卡之后,老数据整体改名 `insight`:**数据保留、只读 + 可搜,不再是抽卡主路径**。新抽卡只写 v4 卡(`card` / `card position`)。

```
memory.talk insight
├── search <query> [--where '<DSL>'] [--limit N] [--json]   # 搜老洞见卡
└── view <insight_id> [--json]                              # 读一条老洞见卡
```

走 v3 改名后的端点 `/v3/insights`(见 [`../../works/v4/card.md`](../../works/v4/card.md#9-与-v3--insight-的共存与迁移))。数据结构沿用 v3 talk-card(`insight` / `rounds` / `stats` / `reviews`),只是前缀 `card_` → `insight_`。

> **只读**:`insight` 没有 create / review 子命令——老数据冻结。要继续往问题图里沉淀,用 [`card`](card.md) / [`review`](review.md)。老洞见可逐条**投影**进 v4 图(一条 insight → 一张卡 + 一个 Position),投影策略见 works §9 步骤三。

## insight search

跟 v3 `search` 同款(撞 `insight` 文本、沉浮排序、DSL 用 v3 字段 `review_up` / `read_count` / `recall_count` 等),只是范围限定在 insight 集合。

```bash
memory.talk insight search "向量库选型" --limit 10
```

DSL 字段沿用 v3(老数据仍带那套 stats),详见 [`../v3/search.md`](../v3/search.md)。

## insight view

```bash
memory.talk insight view insight_01jz8k2m
```

输出沿用 v3 卡的读取形态(`insight` 文本 + 展开的 rounds + stats + reviews),见 [`../v3/read.md`](../v3/read.md) / [`../../structure/v3/talk-card.md`](../../structure/v3/talk-card.md)。

## 错误

| 情况 | 行为 |
|---|---|
| `insight_id` 前缀错 / 不存在 | `error: insight '<id>' not found`,exit 1 |
| 在 `insight` 上调写操作 | `error: insight is read-only; use 'card' / 'review'`,exit 1 |
