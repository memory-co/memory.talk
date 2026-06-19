# Review (v4)

对一个 **Position(答案)** 的一次**表态** —— 带 session 证据 + 方向(`argument` ∈ `+1`/`0`/`−1`)+ 一句话说明。**append-only**,创建即冻。

v4 **沿用 v3 的 review**,只把 target 从 `card_id` 换成 `position_id`(顶踩下放到答案粒度)。其中 **`argument≠0` 的 review 就是一条 IBIS Argument**(pro/con);`argument=0` 是中立观察,不是 argument。

> v3 用 `score`,v4 改叫 `argument`(语义对齐 IBIS,取值不变:`1`/`0`/`-1`)。

机制见 [`../../works/v4/card.md`](../../works/v4/card.md) §3。被表态的 Position 见 [card.md](card.md)。

## Schema

```json
{
  "review_id": "review_01jzp3nq",
  "position_id": "pos_01jzr5kq",
  "card_id": "card_01jz8k2m",
  "session_id": "sess_def456",
  "indexes": "20-25",
  "argument": 1,
  "comment": "三个月后再确认:简洁优先在日常问答里确实更顺",
  "created_at": "2026-06-19T09:14:22Z"
}
```

## 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `review_id` | string | 自动 | `review_<ULID>`,不提供则自动生成 |
| `position_id` | string | 是 | **被表态的 Position**(target);`pos_<...>` |
| `card_id` | string | 自动 | 冗余 = `positions.card_id`。源不可变(答案不换卡)→ 永不漂移,省「这张卡所有 review」的 join。写入时由服务端按 `position_id` 回填 |
| `session_id` | string | 是 | 本次表态所在 session,`sess_<...>`。**单 session**(对比 card 的出处可跨多 session) |
| `indexes` | string | 是 | 证据 round 范围;语法 `"20-25"`(闭区间)/ `"3,7,12"`(离散),严格单调递增、不越界 |
| `argument` | integer | 是 | 方向:`1` 支持(顶 / pro)/ `0` 中立 / `-1` 反对(踩 / con)。其它值报错 |
| `comment` | string | 否 | 一句话归因;`argument=0` 时强烈建议填,服务端不强制 |
| `created_at` | string | 自动 | ISO 8601 |

`argument` ↔ Position 计数:`+1` → `up_count++`,`-1` → `down_count++`,`0` → `neutral_count++`。credence 由 `up_count`/`down_count` 现算(中立、沉默都不动 credence)。

## `(position_id, session_id)` 唯一性

**不去重**。同一对 `(position_id, session_id)` 允许多条 review —— 一次会话里在不同位置可能对同一答案表态多次(早期反对、深入后转支持),每条由 `indexes` 区分。

## 跟 CardSession 的边界

两者都带 `(session_id, indexes)`、都源自旁白标注(session-annotation.md),但角色不同:

| | Review | CardSession |
|---|---|---|
| 记的是 | 对某答案**顶/踩/中立**(表态) | 某 session **启发/生出**了卡 / 答案(出处) |
| 何时产生 | hit 命中已有答案 → 一条 review | miss 建新卡、冲突建新竞争 Position → 一条 card_session |
| target | `position_id` | `card_id`(+ 可选 `position_id`) |

见 [card-session.md](card-session.md) 与 [`../../works/v4/card.md`](../../works/v4/card.md) §6。

## 存储

review **不进文件罐**(沿用 v3 review 的存法:有自己的 canonical),只在 SQLite。

```sql
-- 对 Position 的带证据表态(沿用 v3 review;argument≠0 即 IBIS Argument)
CREATE TABLE reviews (
  review_id   TEXT PRIMARY KEY,            -- review_<ulid>
  position_id TEXT NOT NULL,               -- 表态哪个答案(target)
  card_id     TEXT NOT NULL,               -- 冗余 = positions.card_id(永不漂移,省 join)
  session_id  TEXT NOT NULL,
  indexes     TEXT NOT NULL,               -- session 证据(哪几个 round)
  argument    INTEGER NOT NULL,            -- 方向:+1 支持 / 0 中立 / -1 反对
  comment     TEXT,
  created_at  TEXT NOT NULL
);
CREATE INDEX idx_reviews_position ON reviews(position_id, created_at DESC);
CREATE INDEX idx_reviews_card     ON reviews(card_id);
```

- **无 FOREIGN KEY**(SQLite 派生索引,容忍悬空)。
- `idx_reviews_position(... created_at DESC)` 同时服务两件事:累加计数、以及排序平手时取「最近更新」(最后一条 review 时间)做 tiebreak。

## 读取

review **没有独立读取入口** —— 没有 `GET /v4/reviews/{id}`。想看某答案 / 某卡的 review,走 `read`(响应里按 `created_at` 倒序带出)。

## 设计取舍

- **不允许撤销 review**:append-only。表态错了就**再写一条相反 `argument` 的 review**(comment 说明原因),让旧 review 也算进历史,后续把它压下去 —— 跟「credence 现算、不存状态」配套。
- **`argument=0` 还要单独存**:中立是「证据相关、但不站现有任何答案的队」的信号;堆多了可能在为一个还没说出来的答案背书(→ 衍生新 Position)。它不动 credence,但保留了这条独立信号。

## 跟 v3 review 的差异

| | v3 review | v4 review |
|---|---|---|
| target | `card_id`(整张卡) | `position_id`(某个答案) |
| 方向字段 | `score`(1/0/-1) | `argument`(1/0/-1,语义对齐 IBIS) |
| 累加到 | `card_stats.review_up/down/neutral` | `positions.up_count/down_count/neutral_count` |
| 冗余键 | — | `card_id`(= positions.card_id,省 join) |
| 文件镜像 | `cards/.../reviews.jsonl` | 同款(review 有自己 canonical,不进卡的不可变核) |
