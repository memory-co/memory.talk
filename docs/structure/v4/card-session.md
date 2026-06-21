# CardSession

**card → session 的出处关系** —— 哪个 session 的**哪条 mark**(的 `#…？`)**建 / 连**了这张卡。这是**卡(问题)级**的出处,经 **mark**。

> 注意区分**两条不同链路**(别混):
> - **card → session**(本表):**经 mark**。卡是因为某条 mark 的 `#…？` 而建 / 连的,所以出处指那条 mark。**同一个 card↔session 可以有多条**(不同 mark 各记一条)。
> - **position → session**(见 [PositionSession](position-session.md)):`mark` **可选**,主走 round `indexes`。答案(Position)本身就是「观点」主体;「哪条 mark 触发的」可顺手记(可选),但硬挂 mark 容易跟答案这个观点重复,所以不强求。

机制见 [`../../works/v4/card.md`](../../works/v4/card.md) §6 / §8;写入口(逐 round mark)见 [`../../works/v4/session-mark.md`](../../works/v4/session-mark.md);mark 寻址见 [SessionMark](session-mark.md)。

## 形态

```json
{
  "card_id": "card_01jz8k2m",
  "session_id": "sess_def456",
  "mark": "m1",
  "indexes": "36-37",
  "created_at": "2026-06-18T14:30:00Z"
}
```

读「`sess_def456` 的**第 1 条 mark**(`sess_def456#m1`)的 `#…？` 建 / 连了 `card_01jz8k2m`,这个问题是从第 36–37 轮读出来的」。**不指向具体 Position** —— 这是卡级关系(答案的出处走 [PositionSession](position-session.md))。

## 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `card_id` | string | 是 | 哪张卡;`card_<...>` |
| `session_id` | string | 是 | 哪个 session;`sess_<...>`。**扁平列、可 join、无 FK** |
| `mark` | string | 是 | 哪条 mark 建 / 连的;mark id `m1`/`m2`(session 内序号)。寻址 `<session_id>#<mark>`,**精确到那条带 `#…？` 的感悟** |
| `indexes` | string | 是 | 这条 `#…？`(issue)在这个 session 里 grounding 的 round(s)——**这个问题是从哪几轮读出来的**;可多个,语法同 [`reviews.indexes`](review.md)(`36-37` / `3,7,12`,严格单调) |
| `created_at` | string | 自动 | ISO 8601 |

## canonical 在哪 —— mark 的 `issues[]`

CardSession **不是原始真相**:它的 canonical 是逐 round mark(`marks/m<n>.yaml`)里每条 mark 的 `issues[]`(`card_id` + `is_new` + `indexes`)。`card_sessions` 表是**从这些 `issues[]` 派生出来的可 join 索引**,回答「这个 session / 这条 mark 建 / 连了哪些卡、从哪几轮」。详见 [`../../works/v4/session-mark.md`](../../works/v4/session-mark.md)。

## 存储

```sql
-- card → session 出处(哪条 mark 建/连了这张卡,从哪几轮);同一 card↔session 可多条(不同 mark)
CREATE TABLE card_sessions (
  card_id     TEXT NOT NULL,   -- 哪张卡
  session_id  TEXT NOT NULL,   -- 哪个 session(扁平,可 join;无 FK)
  mark        TEXT NOT NULL,   -- 哪条 mark 的 id(m1 / m2 …;寻址 = session_id#mark)
  indexes     TEXT NOT NULL,   -- 这条 #…？ grounding 的 round(s)(可多个;"36-37" / "3,7,12")
  created_at  TEXT NOT NULL,
  PRIMARY KEY (card_id, session_id, mark)
);
CREATE INDEX idx_card_sessions_session ON card_sessions(session_id);        -- 反查「这个 session 建/连了哪些卡」
CREATE INDEX idx_card_sessions_mark    ON card_sessions(session_id, mark);  -- 反查「这条 mark(sess#m1)建/连了哪些卡」
```

- **无 FOREIGN KEY**(SQLite 派生索引,容忍悬空;canonical 是 `marks/*.yaml`)。
- **`mark` 必选,是这条链路的 key/handle**:颗粒度**必须到 mark**——支撑 mark 里 `#…？` 的**双向关联**(从卡查「哪些 mark 提了它」、从 mark 查「建/连了哪些卡」)。`indexes` 是这个 issue 的 grounding round(s),**额外记录、不进 PK**。对比 [position_sessions](position-session.md):那条链路 key 是 `indexes`、`mark` 可选。
- **PK `(card_id, session_id, mark)`**:同一张卡可被同一 session 的**多条不同 mark** 建 / 连(各记一条);也支持多 session。`indexes` 是该行的数据列。**同一份 mark 里多条 round 命中同一张卡 → 合并成一行**(不违反 PK),`indexes` 把那几轮并起来(如 round 37 & 50 → `"37,50"`)。
- **不指向具体 Position**:这是卡级关系。答案级出处是另一条链路 → [PositionSession](position-session.md)。

## 跟 v3 的对应

v3 没有独立 card↔session 表(隐式在 `card.rounds[].session_id`)。v4 拆成两条显式链路:**card→session**(本表,经 mark)+ **position→session**([PositionSession](position-session.md),经 indexes)。canonical 分别是 mark 的 `issues[]` 和 Position 的 `--source`。
