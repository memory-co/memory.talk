# PositionSession

**position → session 的出处关系** —— 这个**答案(Position)**来自某个 session 的**哪几轮**(`indexes`)。这是**答案级**的出处,**不经 mark**。

> 为什么不经 mark(对照 [CardSession](card-session.md)):**Position 本身就是「观点」主体**。答案的出处是「它从哪几轮对话里长出来的」(round `indexes`),直接 position→session 就够了。再挂一条 mark = 又引入一个「观点」,跟 Position 重复——所以这条链路**不过 mark**。
>
> 对比:
> - **card → session**:经 **mark**(某条 mark 的 `#…？` 建/连了卡)。见 [CardSession](card-session.md)。
> - **position → session**(本表):经 **round `indexes`**,无 mark。

写入口:[`card position --source <session_id>:<indexes>`](../../cli/v4/card.md#card-position)(给答案标出处,可多 session)。机制见 [`../../works/v4/card.md`](../../works/v4/card.md) §6 / §8。

## 形态

```json
{
  "position_id": "pos_01jzr5kq",
  "card_id": "card_01jz8k2m",
  "session_id": "sess_def456",
  "indexes": "11-15",
  "created_at": "2026-06-18T14:30:00Z"
}
```

读「答案 `pos_01jzr5kq` 来自 `sess_def456` 的第 11–15 轮」。**没有 `mark`**。

## 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `position_id` | string | 是 | 哪个答案;`pos_<...>` |
| `card_id` | string | 是 | 答案属于哪张卡;`card_<...>`。冗余缓存(= `positions.card_id`),服务端从 `position_id` 回填 |
| `session_id` | string | 是 | 哪个 session;`sess_<...>`。**扁平列、可 join、无 FK** |
| `indexes` | string | 是 | 答案来自这个 session 的哪几轮(语法同 [`reviews.indexes`](review.md):`11-15` / `3,7,12`,严格单调) |
| `created_at` | string | 自动 | ISO 8601 |

## 存储

```sql
-- position → session 出处(答案来自这个 session 的哪几轮);支持多 session
CREATE TABLE position_sessions (
  position_id TEXT NOT NULL,   -- 哪个答案
  card_id     TEXT NOT NULL,   -- 冗余(= positions.card_id)
  session_id  TEXT NOT NULL,   -- 哪个 session(扁平,可 join;无 FK)
  indexes     TEXT NOT NULL,   -- 答案来自的 round 区间
  created_at  TEXT NOT NULL,
  PRIMARY KEY (position_id, session_id)
);
CREATE INDEX idx_position_sessions_session ON position_sessions(session_id);  -- 反查「这个 session 启发了哪些答案」
```

- **无 FOREIGN KEY**(SQLite 派生索引,容忍悬空)。
- **PK `(position_id, session_id)`**:一个答案对一个 session 一条出处(`indexes` 是引用的轮次);多个 `--source` 给不同 session → 多条。
- **无 `mark`**:答案级出处不经 mark(理由见顶部)。

## 与 reviews.indexes 的区别

| | `position_sessions.indexes` | [`reviews.indexes`](review.md) |
|---|---|---|
| 答什么 | 这个**答案从哪几轮长出来**(出处 / 来源) | 这条**表态(顶/踩)以哪几轮为证据**(evidence) |
| 主体 | Position(答案) | Review(对某 Position 的一次表态) |

**出处用 `position_sessions`,证据用 `reviews`,启发用 `card_sessions`(mark)** —— 三条线各司其职。
