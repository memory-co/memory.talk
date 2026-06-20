# CardSession

**card↔session 的出处关系** —— 哪个 session(的**哪条 mark**)**启发 / 生出**了这张卡 / 这个答案。跟 [CardLink](card-link.md)(card↔card)平行:`card_links` 管卡之间,`card_sessions` 管卡↔会话。**支持多 session / 多 mark**。

机制见 [`../../works/v4/card.md`](../../works/v4/card.md) §6 / §8;写入口(逐 round mark)见 [`../../works/v4/session-mark.md`](../../works/v4/session-mark.md)。

> **设计调整(未实施)**:出处从旧设计的 `(session_id, indexes)`(指向 round 区间)改成 **`(session_id, mark)`**——`mark` 是 mark 的 id `m1`/`m2`(session 内序号),寻址 `<session_id>#<mark>`(如 `sess_def456#m1`)。mark **不是一等 id**,是 [session 的附属](../../works/v4/session-mark.md#7-mark-的寻址session_idid--session-的附属不是一等-id),`m<n>` 直接当文件名(`marks/m1.yaml`)。当前已落地的实现仍是 `indexes` 那版;本文描述的是 `mark` 目标设计,落地时连 mark 的存储 / 解析一起做。

## 形态

```json
{
  "card_id": "card_01jz8k2m",
  "session_id": "sess_def456",
  "mark": "m1",
  "position_id": "pos_01jzr5kq",
  "created_at": "2026-06-18T14:30:00Z"
}
```

读「`sess_def456` 里**第 1 条 mark**(`sess_def456#m1`)启发了 `card_01jz8k2m` 的答案 `pos_01jzr5kq`」。`position_id` 为 `""` 时表示关联到**问题 / 卡本身**(而非某个具体答案)。round 不再冗存——它是 mark 的属性,要时从 mark 文件取。

## 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `card_id` | string | 是 | 哪张卡;`card_<...>` |
| `session_id` | string | 是 | 哪个 session;`sess_<...>`。**扁平列、可 join、无 FK** —— 这是它跟「把出处塞进 JSON blob」的关键区别 |
| `mark` | string | 是 | 哪条 mark 启发的;mark id `m1`/`m2`(session 内序号)。寻址 = `<session_id>#<mark>`,**精确到那句带 `#…？` 的感悟**;round 由 mark 派生 |
| `position_id` | string | 否 | 启发了哪个答案;`pos_<...>` 或 `""`(= 关联到问题/卡本身)。默认 `""` |
| `created_at` | string | 自动 | ISO 8601 |

## canonical 在哪 —— mark 的 `questions[]`

CardSession **不是原始真相**:它的 canonical 是逐 round mark 里每条 mark(`marks/m<n>.yaml`)的 `questions[]`(`card_id` + `is_new`),落在 session 的 `marks/` 目录(file)。`card_sessions` 表是**从这些 `questions[]` 派生出来的可 join 索引**,回答「这个 session / 这条 mark 启发了哪些卡 / 答案」。详见 [`../../works/v4/session-mark.md`](../../works/v4/session-mark.md)。

所以:**每条 `card_sessions` 的 `(session_id, mark)` 永远指向 session-mark 里那条带 `#…？` 的 mark**,不是凭空来的。它跟 [reviews](review.md) 是 mark 机制的两个写出口 —— card_sessions 记「出处 / 启发」(miss→新卡、关联→老卡),reviews 记「顶/踩/中立」。**启发用 mark(`sess#m1`),证据(review)用 round(`indexes`)。**

## 存储

```sql
-- card ↔ session 出处(哪条 mark 启发了这张卡/哪个答案);支持多 session / 多 mark
CREATE TABLE card_sessions (
  card_id     TEXT NOT NULL,             -- 哪张卡
  session_id  TEXT NOT NULL,             -- 哪个 session(扁平,可 join;无 FK)
  mark        TEXT NOT NULL,             -- 哪条 mark 的 id(m1 / m2 …;寻址 = session_id#mark)
  position_id TEXT NOT NULL DEFAULT '',  -- 启发了哪个答案('' = 关联到问题/卡本身)
  created_at  TEXT NOT NULL,
  PRIMARY KEY (card_id, session_id, mark, position_id)
);
CREATE INDEX idx_card_sessions_session ON card_sessions(session_id);        -- 反查「这个 session 启发了哪些卡/答案」
CREATE INDEX idx_card_sessions_mark    ON card_sessions(session_id, mark);  -- 反查「这条 mark(sess#m1)启发了哪些卡/答案」
```

- **无 FOREIGN KEY**(SQLite 派生索引,容忍悬空)。
- PK `(card_id, session_id, mark, position_id)`:同一张卡可被多条 mark(乃至多 session)启发;同一条 mark 也可启发同卡的问题 + 答案(不同 `position_id`)。
- `idx_card_sessions_mark`(`session_id, mark`):支持「拿一条 mark(`sess_xxx#m1`),反查它建/连了哪些卡」。

## 跟 v3 的对应

v3 没有独立的 card↔session 表:card↔session 隐式在 `card.rounds[].session_id` 里。v4 把它显式化成 `card_sessions`(出处)+ mark 的 `questions[]`(canonical)。v3 card 投影进 v4 图时,其 `rounds` → 一条 `card_sessions`(见 [`../../works/v4/card.md`](../../works/v4/card.md) §9 步骤三)。
