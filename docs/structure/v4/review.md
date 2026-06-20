# Review (v4)

对一个**可治理对象**的一次**表态** —— 带 session 证据 + 方向(`argument` ∈ `+1`/`0`/`−1`)+ 一句话说明。**append-only**,创建即冻。

v4 **沿用 v3 的 review**,只把 target 从整张卡(`card_id`)下放到更细的粒度。target 有**两种**(都寻址 `card_id#<分片>`,由分片判型):

| target_kind | target | 寻址 | 顶踩累加到 |
|---|---|---|---|
| `position` | 某张卡的某个 **Position**(答案) | `card_id#p<n>` | 那个 Position 的 `up/down/neutral_count` |
| `link` | 某张卡的某条 **CardLink**(IBIS 边) | `card_id#l<n>` | 那条 Link 的 `up/down/neutral_count` |

**`target_kind` 从 `#p`/`#l` 分片派生**(`#p` → position、`#l` → link),不必客户端显式给。两种 target 都是受治理对象(Position 答案对不对、Link 这条边成立不成立),共用同一套 review / credence。其中 **`argument≠0` 的 review 就是一条 IBIS Argument**(pro/con);`argument=0` 是中立观察,不是 argument。

> v3 用 `score`,v4 改叫 `argument`(语义对齐 IBIS,取值不变:`1`/`0`/`-1`)。
>
> **credence 对 Position 和 Link 都适用**,但语义不同:Position credence 给答案**排座次**(择优,选当下答案);Link credence 给边**定去留**(存在即合理,过阈值才显示)。见 [card-link.md](card-link.md) 顶部说明。

机制见 [`../../works/v4/card.md`](../../works/v4/card.md) §3 / §4。被表态的 Position 见 [card.md](card.md),Link 见 [card-link.md](card-link.md)。

## Schema

```json
{
  "review_id": "review_01jzp3nq",
  "card_id": "card_01jz8k2m",
  "target": "p1",
  "target_kind": "position",
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
| `card_id` | string | 是 | **被表态对象所属的卡**;`card_<...>`。跟 `target` 一起定位(寻址 `card_id#target`) |
| `target` | string | 是 | **被表态对象** 在卡内的分片:Position = `p<n>`(target = `card_id#p<n>`)或 Link = `l<n>`(target = `card_id#l<n>`)。两者都无独立 id |
| `target_kind` | string | 自动 | `position` / `link`,从 `target` 的 `#p`/`#l` 前缀派生并落列,便于按被表态类型过滤 |
| `session_id` | string | 是 | 本次表态所在 session,`sess_<...>`。**单 session**(对比 card 的出处可跨多 session) |
| `indexes` | string | 是 | 证据 round 范围;语法 `"20-25"`(闭区间)/ `"3,7,12"`(离散),严格单调递增、不越界 |
| `argument` | integer | 是 | 方向:`1` 支持(顶 / pro)/ `0` 中立 / `-1` 反对(踩 / con)。其它值报错 |
| `comment` | string | 否 | 一句话归因;`argument=0` 时强烈建议填,服务端不强制 |
| `created_at` | string | 自动 | ISO 8601 |

`argument` ↔ target 计数:`+1` → `up_count++`,`-1` → `down_count++`,`0` → `neutral_count++`(累加到 `target` 指向的那个 Position 或 Link)。credence 由 `up_count`/`down_count` 现算(中立、沉默都不动 credence)。

## `(card_id, target, session_id)` 唯一性

**不去重**。同一对 `(card_id, target, session_id)` 允许多条 review —— 一次会话里在不同位置可能对同一 Position / Link 表态多次(早期反对、深入后转支持),每条由 `indexes` 区分。

## 跟 CardSession 的边界

两者都带 `(session_id, indexes)`、都源自旁白标注(session-mark.md),但角色不同:

| | Review | CardSession |
|---|---|---|
| 记的是 | 对某答案 / 某边**顶/踩/中立**(表态) | 某 session **启发/生出**了卡 / 答案(出处) |
| 何时产生 | hit 命中已有 Position / Link → 一条 review | miss 建新卡、冲突建新竞争 Position → 一条 card_session |
| target | `card_id` + `target`(`card_id#p<n>` 或 `card_id#l<n>`) | `card_id`(+ 可选 `position` = `p<n>`) |

见 [card-session.md](card-session.md) 与 [`../../works/v4/card.md`](../../works/v4/card.md) §6。

## 存储

review **不进文件罐**(沿用 v3 review 的存法:有自己的 canonical),只在 SQLite。

```sql
-- 对 Position 或 Link 的带证据表态(沿用 v3 review;argument≠0 即 IBIS Argument)
CREATE TABLE reviews (
  review_id   TEXT PRIMARY KEY,            -- review_<ulid>
  card_id     TEXT NOT NULL,               -- target 所属卡(= positions/card_links 的 card_id)
  target      TEXT NOT NULL,               -- 被表态对象在卡内的分片:p<n>(Position)或 l<n>(Link);target = card_id#target
  target_kind TEXT NOT NULL,               -- 'position' | 'link',从 target 的 #p/#l 前缀派生
  session_id  TEXT NOT NULL,
  indexes     TEXT NOT NULL,               -- session 证据(哪几个 round)
  argument    INTEGER NOT NULL,            -- 方向:+1 支持 / 0 中立 / -1 反对
  comment     TEXT,
  created_at  TEXT NOT NULL
);
CREATE INDEX idx_reviews_target ON reviews(card_id, target, created_at DESC);
CREATE INDEX idx_reviews_card   ON reviews(card_id);
```

- **无 FOREIGN KEY**(SQLite 派生索引,容忍悬空)。
- `idx_reviews_target(card_id, target, ... created_at DESC)` 同时服务两件事:累加某个 Position / Link 的计数、以及排序平手时取「最近更新」(最后一条 review 时间)做 tiebreak。
- `target_kind` 不是必填——服务端从 `target` 的 `#p`/`#l` 前缀派生后落列;它只是冗余的过滤键(「列出所有对 Link 的表态」直接按它过滤)。

## 读取

review **没有独立读取入口** —— 没有 `GET /v4/reviews/{id}`。想看某 Position / Link / 某卡的 review,走 `read`(`card_id#p<n>` / `card_id#l<n>` / `card_id`;响应里按 `created_at` 倒序带出)。

## 不变性

- **不允许撤销 review**:append-only。表态错了就**再写一条相反 `argument` 的 review**(comment 说明原因)。
- **`argument=0`(中立)单独计数**:不动 credence(不进 `up`/`down`);中立堆积可离线衍生出新 Position(机制见 [`../../works/v4/card.md`](../../works/v4/card.md) §3 末)。

## 跟 v3 review 的差异

| | v3 review | v4 review |
|---|---|---|
| target | `card_id`(整张卡) | `card_id` + `target`(某卡的某个 Position `#p<n>` 或某条 Link `#l<n>`) |
| 方向字段 | `score`(1/0/-1) | `argument`(1/0/-1,语义对齐 IBIS) |
| 累加到 | `card_stats.review_up/down/neutral` | `positions` 或 `card_links` 的 `up_count/down_count/neutral_count`(按 `target_kind`) |
| 冗余键 | — | `card_id`(= 被表态对象的卡,扁平存,省 join)+ `target_kind`(position/link) |
| 文件镜像 | `cards/.../reviews.jsonl` | 同款(review 有自己 canonical,不进卡的不可变核) |
