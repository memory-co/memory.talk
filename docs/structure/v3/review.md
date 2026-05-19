# Review

对 card 的"回帖" —— 论坛动力学(`../../cli/v3/README.md` §3)里的核心新输入。**append-only**,创建即冻结;关联的 card stats 由后端实时维护。

## Schema

```json
{
  "review_id": "review_01jzr5kq",
  "card_id": "card_01jz8k2m",
  "session_id": "sess_def456",
  "indexes": "20-25",
  "score": 1,
  "comment": "三个月后再次确认 LanceDB 选型有效——生产稳定运行,SQLite + LanceDB 混合栈跑顺",
  "created_at": "2026-05-01T09:14:22Z"
}
```

## 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `review_id` | string | 自动 | `review_<ULID>`,不提供则自动生成 |
| `card_id` | string | 是 | 被 review 的 card,必须是 `card_<...>`;不存在返 400 |
| `session_id` | string | 是 | 本次 review 所在的 session,必须是 `sess_<...>`。**单 session**:一条 review 只挂一个 session(对比 card 的 `rounds` 可跨多 session) |
| `indexes` | string | 是 | 证据 round 范围,语法跟 [Talk-Card 的 rounds.indexes](talk-card.md) 一致(`"20-25"` 区间 / `"3,7,12"` 离散列表) |
| `score` | integer | 是 | `1` 支持 / `0` 中立(纯备注) / `-1` 反对。其它值报错 |
| `comment` | string \| null | 否 | 说明 review 的人话。`score=0` 时强烈建议填(否则信号弱)。后端不强制 |
| `created_at` | string | 自动 | ISO 8601 |

### score 语义

| 值 | 论坛术语 | 沉浮影响 | 计数器 |
|---|---|---|---|
| `1` | 赞 + "对,我就这么想的" | 抬升 | `review_up += 1`, `review_count += 1` |
| `-1` | 踩 + "其实我不这么想" | 沉降 | `review_down += 1`, `review_count += 1` |
| `0` | 楼下歪楼但提到了主题 | **不影响沉浮**(默认公式权重为 0) | `review_neutral += 1`, `review_count += 1` |

详见 [Talk-Card#Stats](talk-card.md#stats) 和 [`../../cli/v3/search.md#排序`](../../cli/v3/search.md#排序)。

### `(card_id, session_id)` 唯一性

**不去重**。同一对 `(card_id, session_id)` 可以有多条 review —— 一次会话里在不同位置可能对同一张 card 表态多次(早期反对、深入后转支持)。每条 review 由 `indexes` 区分。

## 存储

### 镜像文件(每个 card 一份汇总)

```
cards/{card_id[5:7]}/{card_id}/reviews.jsonl
```

每行一个 review JSON(append-only),按 `created_at` 顺序追加。

### SQLite(查询主路径)

```sql
CREATE TABLE reviews (
  review_id    TEXT PRIMARY KEY,
  card_id      TEXT NOT NULL,
  session_id   TEXT NOT NULL,
  indexes      TEXT NOT NULL,         -- 原样存,如 "20-25" / "3,7,12"
  score        INTEGER NOT NULL,      -- 1 / 0 / -1
  comment      TEXT,                  -- 可 NULL
  created_at   TIMESTAMP NOT NULL,
  FOREIGN KEY (card_id) REFERENCES cards(card_id)
);

CREATE INDEX idx_reviews_card_id ON reviews(card_id);
CREATE INDEX idx_reviews_session_id ON reviews(session_id);
CREATE INDEX idx_reviews_created_at ON reviews(created_at);
```

`indexes` 字符串原样存(不展开成多行 round 引用),因为 review 的语义是"我在这一段 rounds 里做出了表态",rounds 范围本身就是信号。

### 事件日志

每条 review 创建时在 `cards/{...}/{card_id}/events.jsonl` 写一条 `reviewed` 事件:

```json
{"event": "reviewed", "review_id": "review_01jzr5kq", "session_id": "sess_def456", "indexes": "20-25", "score": 1, "ts": "2026-05-01T09:14:22Z"}
```

`comment` **不进事件日志**(原文在 reviews.jsonl + SQLite 已经有);events.jsonl 只保留事件骨架。

## 读取

review **不暴露独立读取入口** —— 不存在 `GET /v3/reviews/{id}`。要看 review 走两条路:

- `POST /v3/read {id: "card_xxx"}` 的响应里 `card.reviews` 字段
- 直接读 `cards/{...}/{card_id}/reviews.jsonl` 文件

理由:review 没有"作为独立对象被检索"的需求。它依附于 card —— 你想知道某张 card 怎么被看待,就 read 这张 card,reviews 跟着一起出来。

## 跟其它对象的关系

```
Review
  │
  ├── card_id ─────────► Card(被 review 的对象)
  │                       │
  │                       └─ stats(被本 review 累加)
  │
  ├── session_id ──────► Session(review 发生的语境)
  │                       │
  │                       └─ rounds[indexes...]:review 引用的证据
  │
  └── (no other refs)
```

跟 [Card.source_cards](talk-card.md#sourcecard) 的对照:

| | source_cards | review |
|---|---|---|
| 谁的字段 | card 自己的 | 独立对象,有 review_id |
| 关联对端 | 另一张 card | 一张 card + 一段 session 证据 |
| 创建时机 | card 创建时一并 | card 创建之**后**,任意时间 |
| 可变性 | immutable | immutable |
| 沉浮影响 | 间接(fork 创建竞争对手) | 直接(改 card.stats,影响排序) |
