# PositionSession

**position → session 的出处关系** —— 这个**答案(Position)**来自某个 session 的**哪几轮**(`indexes`)。这是**答案级**的出处,**主走 round `indexes`、`mark` 可选**。

> 为什么 `mark` 在这条链路是**可选**的(对照 [CardSession](card-session.md) 的 `mark` 必选):**Position 本身就是「观点」主体**。答案的主出处是「它从哪几轮对话里长出来的」(round `indexes`),这就够了;「是不是某条 mark 触发的」可以**顺手记一下(可选)**,但硬挂 mark 容易跟「答案这个观点本身」重复,所以不强求。
>
> 对比:
> - **card → session**:`mark` **必选**——卡是某条 mark 的 `#…？` 建/连的,要支撑 `#…？` 双向关联。见 [CardSession](card-session.md)。
> - **position → session**(本表):`indexes` **必填** + `mark` **可选**。

写入口:[`card position --source <session_id>:<indexes>`](../../cli/v4/card.md#card-position)(给答案标出处,可多 session)。机制见 [`../../works/v4/card.md`](../../works/v4/card.md) §6 / §8。

## 形态

```json
{
  "position_id": "pos_01jzr5kq",
  "card_id": "card_01jz8k2m",
  "session_id": "sess_def456",
  "indexes": "11-15",
  "mark": "",
  "created_at": "2026-06-18T14:30:00Z"
}
```

读「答案 `pos_01jzr5kq` 来自 `sess_def456` 的第 11–15 轮」。`indexes` 是主出处;`mark` **可选**(给了就额外指明「这答案是哪条 mark 触发的」,`""` = 没记)。

## 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `position_id` | string | 是 | 哪个答案;`pos_<...>` |
| `card_id` | string | 是 | 答案属于哪张卡;`card_<...>`。冗余缓存(= `positions.card_id`),服务端从 `position_id` 回填 |
| `session_id` | string | 是 | 哪个 session;`sess_<...>`。**扁平列、可 join、无 FK** |
| `indexes` | string | **是** | 答案来自这个 session 的哪几轮(语法同 [`reviews.indexes`](review.md):`11-15` / `3,7,12`,严格单调)。**主出处** |
| `mark` | string | **否(可选)** | 这答案是哪条 mark 触发的(mark id `m<n>`,寻址 `session_id#mark`);`""` = 没记。**颗粒度到 mark 在 position 这条链路是可选的**(对比 [card_sessions](card-session.md) 的 `mark` 必选) |
| `created_at` | string | 自动 | ISO 8601 |

## 存储

```sql
-- position → session 出处(答案来自这个 session 的哪几轮;mark 可选);支持多 session
CREATE TABLE position_sessions (
  position_id TEXT NOT NULL,             -- 哪个答案
  card_id     TEXT NOT NULL,             -- 冗余(= positions.card_id)
  session_id  TEXT NOT NULL,             -- 哪个 session(扁平,可 join;无 FK)
  indexes     TEXT NOT NULL,             -- 答案来自的 round 区间(主出处,必填)
  mark        TEXT NOT NULL DEFAULT '',  -- 可选:哪条 mark 触发的('' = 没记)
  created_at  TEXT NOT NULL,
  PRIMARY KEY (position_id, session_id, mark)
);
CREATE INDEX idx_position_sessions_session ON position_sessions(session_id);  -- 反查「这个 session 启发了哪些答案」
```

- **无 FOREIGN KEY**(SQLite 派生索引,容忍悬空)。
- **`indexes` 必填、`mark` 可选**:答案级出处的颗粒度**主要到 round**(`indexes`);到 mark 是可选增量。对比 [card_sessions](card-session.md):那条链路 `mark` **必选**(要支撑 `#…？` 的双向关联)。
- **PK `(position_id, session_id, mark)`**:`mark=''` 是「只记到 round」的那条;给了 mark 则可与无-mark 行 / 不同 mark 行并存。多个 `--source` 给不同 session → 多条。

## 与 reviews.indexes 的区别

| | `position_sessions.indexes` | [`reviews.indexes`](review.md) |
|---|---|---|
| 答什么 | 这个**答案从哪几轮长出来**(出处 / 来源) | 这条**表态(顶/踩)以哪几轮为证据**(evidence) |
| 主体 | Position(答案) | Review(对某 Position 的一次表态) |

**出处用 `position_sessions`,证据用 `reviews`,启发用 `card_sessions`(mark)** —— 三条线各司其职。
