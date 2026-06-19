# link

卡与卡之间的 **IBIS 边**(`card_links`)——问题图的关联主干(细化 / 取代 / 质疑 / 引出 / 泛关联)。

```
memory.talk link
├── create <from_card_id> <type> <target_id> [--json]    # 建一条有向边
└── list <card_id> [--json]                              # 列一张卡的边(出 + 入)
```

调 [`POST /v4/card-links`](../../api/v4/card-links.md)。字段语义见 [`../../structure/v4/card-link.md`](../../structure/v4/card-link.md)。

> 边连的是**卡(问题)**:主体是 `from_card_id`(`card_<…>`)。`target_id` 一般是另一张卡(`card_<…>`);只有 `suggested_by` 允许指向一个答案(`pos_<…>`)——「这个答案勾出了那个新问题」。

## link create

```bash
memory.talk link create <from_card_id> <type> <target_id> [--json]
```

### type 取值

| type | 含义 | 方向 |
|---|---|---|
| `specializes` | from 是 target 的更窄版(子问题,DAG 非树) | 有向 |
| `suggested_by` | from 被 target 引出来(出处 / 因果);target 可为 `pos_` | 有向 |
| `questions` | from 质疑 target 的前提 / 框架 | 有向 |
| `replaces` | from 重述并取代 target(**保留历史**,不删 target) | 有向 |
| `related` | 兜底泛关联 | 无向 |

- 同一 `(from_card_id, type)` 下可挂多条(如 `specializes` 多父)。
- `related` 无向:写时规范化两端顺序,只存一遍(`link create A related B` 与 `B related A` 等价、不重复落)。
- **不校验 `target_id` 是否存在**:SQLite 是派生索引,容忍悬挂引用,从不加 FOREIGN KEY(target 可能后到 / 已删,图层照样成立)。

### 输出

````markdown
ok: `card_01jz8k2m` —specializes→ `card_01jzsub`
````

```json
{"status": "ok", "card_id": "card_01jz8k2m", "type": "specializes", "target_id": "card_01jzsub"}
```

## link list

列一张卡相关的所有边——它**指出去的**(本卡为主体)和**指过来的**(别的卡指本卡)。

```bash
memory.talk link list <card_id> [--json]
```

### 输出 — Markdown

````markdown
# links of `card_01jz8k2m`

**out:**
- specializes → `card_01jzsub`
- related — `card_01jzrel`

**in:**
- replaces ← `card_01jzold`
````

```json
{
  "card_id": "card_01jz8k2m",
  "out": [{"type": "specializes", "target_id": "card_01jzsub"}],
  "in":  [{"type": "replaces", "from_card_id": "card_01jzold"}]
}
```

## 错误

| 情况 | 行为 |
|---|---|
| `from_card_id` 不存在 | `error: card '<id>' not found`,exit 1 |
| `type` 不在五类型内 | `error: unknown link type '<t>'`,exit 1 |
| `target_id` 前缀错(非 `card_`/`pos_`,或 `pos_` 用在非 `suggested_by`) | `error: invalid target_id`,exit 1 |
| 同一 `(from, type, target)` 已存在 | `error: link already exists`,exit 1 |

> `issue` 层的 `replaces`(问题取代问题)≠ Position 层的 `forked_from_position_id`(答案分叉),别混,见 [`../../structure/v4/card-link.md`](../../structure/v4/card-link.md)。
