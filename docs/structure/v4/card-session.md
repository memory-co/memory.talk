# CardSession

**card↔session 的出处关系** —— 哪个 session(的哪几条旁白 round)**启发 / 生出**了这张卡 / 这个答案。跟 [CardLink](card-link.md)(card↔card)平行:`card_links` 管卡之间,`card_sessions` 管卡↔会话。**支持多 session**。

机制见 [`../../works/v4/card.md`](../../works/v4/card.md) §6 / §8;写入口(旁白)见 [`../../works/v4/session-annotation.md`](../../works/v4/session-annotation.md)。

## 形态

```json
{
  "card_id": "card_01jz8k2m",
  "session_id": "sess_def456",
  "position_id": "pos_01jzr5kq",
  "indexes": "11-15",
  "created_at": "2026-06-18T14:30:00Z"
}
```

读「sess_def456 的第 11–15 轮旁白启发了 card_01jz8k2m 的答案 pos_01jzr5kq」。`position_id` 为 `""` 时表示关联到**问题 / 卡本身**(而非某个具体答案)。

## 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `card_id` | string | 是 | 哪张卡;`card_<...>` |
| `session_id` | string | 是 | 哪个 session;`sess_<...>`。**扁平列、可 join、无 FK** —— 这是它跟「把出处塞进 JSON blob」的关键区别 |
| `position_id` | string | 否 | 启发了哪个答案;`pos_<...>` 或 `""`(= 关联到问题/卡本身)。默认 `""` |
| `indexes` | string | 是 | 那个 session 里**标了 `#问题` 的旁白 round**(语法同 [`reviews.indexes`](review.md)) |
| `created_at` | string | 自动 | ISO 8601 |

## canonical 在哪 —— 旁白的 `questions[]`

CardSession **不是原始真相**:它的 canonical 是旁白(逐 round 标注)里每行的 `questions[]`(`card_id` + `is_new` + 这条 round 的 index),落在 session 的标注文件(file)。`card_sessions` 表是**从这些 `questions[]` 派生出来的可 join 索引**,回答「这个 session 启发了哪些卡 / 答案」。详见 [`../../works/v4/session-annotation.md`](../../works/v4/session-annotation.md)。

所以:**每条 `card_sessions` 的 `(session_id, indexes)` 永远指向 session-annotation 里被标注的旁白 round**,不是凭空来的。它跟 [reviews](review.md) 是旁白机制的两个写出口 —— card_sessions 记「出处 / 启发」(miss→新卡、冲突→新竞争 Position),reviews 记「顶/踩/中立」(hit)。

## 存储

```sql
-- card ↔ session 出处(哪个 session 启发了这张卡/哪个答案);支持多 session
CREATE TABLE card_sessions (
  card_id     TEXT NOT NULL,               -- 哪张卡
  session_id  TEXT NOT NULL,               -- 哪个 session(扁平,可 join;无 FK)
  position_id TEXT NOT NULL DEFAULT '',    -- 启发了哪个答案('' = 关联到问题/卡本身)
  indexes     TEXT NOT NULL DEFAULT '[]',  -- 那个 session 标了 #问题 的旁白 round(同 reviews.indexes)
  created_at  TEXT NOT NULL,
  PRIMARY KEY (card_id, session_id, position_id)  -- 同一卡可挂多 session;同一 session 也可启发多答案
);
CREATE INDEX idx_card_sessions_session ON card_sessions(session_id);  -- 反查「这个 session 启发了哪些卡/答案」
```

- **无 FOREIGN KEY**(SQLite 派生索引,容忍悬空)。
- PK `(card_id, session_id, position_id)`:同一张卡可挂多个 session;同一 session 也可启发同卡的多个答案(不同 `position_id`)。
- `idx_card_sessions_session`:支持「拿一个 session,反查它启发过哪些卡 / 答案」—— 这正是 v3「出处」从 JSON blob 改成扁平表后**能 join** 的收益。

## 为什么独立成表(而非内联进 Position)

「出处」曾内联在 Position(单 session 的 `inspired_by`),但:① 一张卡 / 一个答案可能由**多个** session 启发;② 出处的 `session_id` 内联进 JSON 没法 join / 建索引。拆成 `card_sessions` 扁平表后,多 session 天然支持,且能跟 `sessions` 表 join。设计推理见 [`../../works/v4/card.md`](../../works/v4/card.md) §8。

## 跟 v3 的对应

v3 没有独立的 card↔session 表:card↔session 隐式在 `card.rounds[].session_id` 里。v4 把它显式化成 `card_sessions`(出处)+ 旁白 `questions[]`(canonical)。v3 card 投影进 v4 图时,其 `rounds` → 一条 `card_sessions`(见 [`../../works/v4/card.md`](../../works/v4/card.md) §9 步骤三)。
