# CardSession

**card → session 的出处关系** —— 哪个 session 的**哪条 mark**(的 `#…？`)**建 / 连**了这张卡。这是**卡(问题)级**的出处,经 **mark**。

> 注意区分**两条不同链路**(别混):
> - **card → session**(本表):**经 mark**。卡是因为某条 mark 的 `#…？` 而建 / 连的,所以出处指那条 mark。**同一个 card↔session 可以有多条**(不同 mark 各记一条)。
> - **position → session**(见 [PositionSession](position-session.md)):**不经 mark**,走 round `indexes`。答案(Position)本身就是「观点」主体;再挂一条 mark 等于又来一个观点、跟 position 重复,所以这条链路直接 position→session、不过 mark。

机制见 [`../../works/v4/card.md`](../../works/v4/card.md) §6 / §8;写入口(逐 round mark)见 [`../../works/v4/session-mark.md`](../../works/v4/session-mark.md);mark 寻址见 [SessionMark](session-mark.md)。

## 形态

```json
{
  "card_id": "card_01jz8k2m",
  "session_id": "sess_def456",
  "mark": "m1",
  "created_at": "2026-06-18T14:30:00Z"
}
```

读「`sess_def456` 的**第 1 条 mark**(`sess_def456#m1`)的 `#…？` 建 / 连了 `card_01jz8k2m`」。**没有 `position_id`** —— 这是卡级关系(答案的出处走 [PositionSession](position-session.md))。

## 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `card_id` | string | 是 | 哪张卡;`card_<...>` |
| `session_id` | string | 是 | 哪个 session;`sess_<...>`。**扁平列、可 join、无 FK** |
| `mark` | string | 是 | 哪条 mark 建 / 连的;mark id `m1`/`m2`(session 内序号)。寻址 `<session_id>#<mark>`,**精确到那条带 `#…？` 的感悟** |
| `created_at` | string | 自动 | ISO 8601 |

## canonical 在哪 —— mark 的 `questions[]`

CardSession **不是原始真相**:它的 canonical 是逐 round mark(`marks/m<n>.yaml`)里每条 mark 的 `questions[]`(`card_id` + `is_new`)。`card_sessions` 表是**从这些 `questions[]` 派生出来的可 join 索引**,回答「这个 session / 这条 mark 建 / 连了哪些卡」。详见 [`../../works/v4/session-mark.md`](../../works/v4/session-mark.md)。

## 存储

```sql
-- card → session 出处(哪条 mark 建/连了这张卡);同一 card↔session 可多条(不同 mark)
CREATE TABLE card_sessions (
  card_id     TEXT NOT NULL,   -- 哪张卡
  session_id  TEXT NOT NULL,   -- 哪个 session(扁平,可 join;无 FK)
  mark        TEXT NOT NULL,   -- 哪条 mark 的 id(m1 / m2 …;寻址 = session_id#mark)
  created_at  TEXT NOT NULL,
  PRIMARY KEY (card_id, session_id, mark)
);
CREATE INDEX idx_card_sessions_session ON card_sessions(session_id);        -- 反查「这个 session 建/连了哪些卡」
CREATE INDEX idx_card_sessions_mark    ON card_sessions(session_id, mark);  -- 反查「这条 mark(sess#m1)建/连了哪些卡」
```

- **无 FOREIGN KEY**(SQLite 派生索引,容忍悬空;canonical 是 `marks/*.yaml`)。
- **PK `(card_id, session_id, mark)`**:同一张卡可被同一 session 的**多条不同 mark** 建 / 连(各记一条);也支持多 session。
- **无 `position_id`**:这是卡级关系。答案级出处是另一条链路 → [PositionSession](position-session.md)。

## 跟 v3 的对应

v3 没有独立 card↔session 表(隐式在 `card.rounds[].session_id`)。v4 拆成两条显式链路:**card→session**(本表,经 mark)+ **position→session**([PositionSession](position-session.md),经 indexes)。canonical 分别是 mark 的 `questions[]` 和 Position 的 `--source`。
