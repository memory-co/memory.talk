# CardLink

**card↔card 的有向边** —— 因 `card ≡ issue`,这就是 IBIS 里 issue↔issue 那套关系(细化 / 引出 / 质疑 / 取代 / 泛关联)。卡↔卡是问题图的**关联主干**;`position` 之间不直接结网。

机制见 [`../../works/v4/card.md`](../../works/v4/card.md) §4。card↔session 的出处关系是另一张表,见 [card-session.md](card-session.md)。

## 形态

一条边 = **主体卡 `card_id` + 类型 `type` + 对端 `target_id`**,非对称(不是对称的 from/to,而是「谁的边」)。

```json
{
  "card_id": "card_01jz8k2m",
  "type": "specializes",
  "target_id": "card_01jzyyyy",
  "target_type": "card",
  "created_at": "2026-06-18T15:00:00Z"
}
```

读「这张卡 = card_01jz8k2m 是 card_01jzyyyy 的更窄版(子问题)」。

## 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `card_id` | string | 是 | **主体卡**(谁的边);`card_<...>` |
| `type` | string | 是 | 边类型,见 [#类型](#类型) |
| `target_id` | string | 是 | 对端 id;多为 `card_<...>`,`suggested_by` 可为一个 Position 地址 `card_<...>#p<n>` |
| `target_type` | string | 自动 | 对端类型:`card` / `position`,从 `target_id` 派生(带 `#p` 分片 → `position`,否则 `card`)并**单独落列**——「列出所有指向 Position 的边」这类查询直接按它过滤,不必解析地址 |
| `created_at` | string | 自动 | ISO 8601 |

## 类型

| `type` | 含义 | 方向 |
|---|---|---|
| `specializes` | A 是 B 的更窄版(子问题,**DAG 非树**) | 有向 |
| `suggested_by` | A 被某节点引出来(出处 / 因果);**对端可为 Position**(答案也能勾出新问题) | 有向 |
| `questions` | A 质疑 B 的前提 / 框架 | 有向 |
| `replaces` | A 重述并取代 B(**保留历史**,不删 B) | 有向 |
| `related` | 兜底泛关联 | 无向 |

> IBIS 关系集**不完备**,可按需补 `depends_on` / `part_of`。未识别 `type` 报 400。
>
> **`replaces`(issue 层)≠ `forked_from`(position 层)**:`replaces` 是一个**问题**重述取代另一个问题;`forked_from` 是同一问题下一个**答案**分叉自另一个答案。两个不同机制,别混。

## 多值 / 方向

- **五类型全多值**:同一 `(card_id, type)` 下可多条(如 `specializes` 多父 → 统一边表、不内联成列)。PK 是 `(card_id, type, target_id)`。
- **`related` 无向**:写时规范化排序(两端按 id 排好)只存一遍,避免 A→B、B→A 双份。

## 存储

```sql
-- 主体卡的有向边(= IBIS issue↔issue,因 card≡issue)
CREATE TABLE card_links (
  card_id    TEXT NOT NULL,               -- 主体卡(谁的边),不是对称 from/to
  type        TEXT NOT NULL,              -- specializes|suggested_by|questions|replaces|related
  target_id   TEXT NOT NULL,              -- 对端 id:多为 card_…;suggested_by 可为 card_…#p<n>(一个 Position)
  target_type TEXT NOT NULL,              -- 'card' | 'position',从 target_id 派生(带 #p 分片 → position)
  created_at  TEXT NOT NULL,
  PRIMARY KEY (card_id, type, target_id)  -- 同一(主体,类型)下可多条;target_type 随 target_id 定,不进 PK
);
```

- **无 FOREIGN KEY**(SQLite 派生索引,容忍悬空)。`target_type`(`card` / `position`)从 `target_id` 派生(带 `#p` 分片 = 一个 Position → `position`,否则 `card`)、单独落列——便于按对端类型过滤,免每次解析地址。
- 关系数据的 canonical 落点(是否也进文件罐)与图整体是否值得 file-canonical 一并待定,见 [`../../works/v4/card.md`](../../works/v4/card.md) §12。

## 反查

「指向某卡 / 某 Position 的边」(入边)需要时另加 `CREATE INDEX ... ON card_links(target_id)`;本表 PK 已覆盖「某主体卡的出边」。

## 跟 v3 source_cards 的差异

| | v3 `source_cards` | v4 `card_links` |
|---|---|---|
| 载体 | card 的内联字段(创建即冻) | 独立表(可后续增边) |
| 关系 | `derives_from` / `supersedes` 两种 | 五类型(IBIS) |
| 对端 | 只 card | card 为主,`suggested_by` 可指 Position(`card_…#p<n>`) |
| 方向 | 单向(本卡 → 源卡) | 有向为主,`related` 无向 |
