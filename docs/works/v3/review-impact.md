# Review 怎么影响 card stats

`POST /v3/reviews` 创建一条 review 时,服务端怎么累加 `card_stats` 的多个 counter + 写跨对象事件链。

相关:
- API: [`../../api/v3/reviews.md`](../../api/v3/reviews.md)
- Review schema: [`../../structure/v3/review.md`](../../structure/v3/review.md)
- Card stats 整体: [forum-dynamics.md](forum-dynamics.md)

## 总体顺序

```
1. 校验 card_id / session_id 存在 + indexes 在 session 范围内
2. 算 review_id(可选传入,或自动生成 review_<ULID>)
3. SQLite tx:
   - INSERT reviews row
   - UPDATE card_stats:
     · review_count += 1
     · 按 score 累加 review_up / review_down / review_neutral 之一
     · updated_at = now
4. append cards/<...>/reviews.jsonl(镜像)
5. append cards/<...>/events.jsonl 的 reviewed 事件
```

第 3 步是单事务,**counters 跟 reviews 行的 INSERT 必须原子**(否则就是 [forum-dynamics.md](forum-dynamics.md) 警告过的 drift 模式)。

## Score → counter 映射

| `score` 取值 | 累加 |
|---|---|
| `+1` | `review_up += 1`, `review_count += 1` |
| `-1` | `review_down += 1`, `review_count += 1` |
| `0` | `review_neutral += 1`, `review_count += 1` |

`review_neutral` 默认在 ranking 公式权重为 0,但仍单独存,允许用户改公式时调用(讨论广度信号)。

## 事件链

| 事件类型 | 写到哪 | 用途 |
|---|---|---|
| `reviewed` | `cards/<...>/events.jsonl` | card 自身视角:我被谁、什么时候、给了什么分 |
| review 行 | `cards/<...>/reviews.jsonl` | card 上所有 review 的镜像,append-only,FYI |
| review 行 | SQLite `reviews` 表 | 查询主路径(SQL JOIN cards 用) |

**Review 是 file-canonical 模式的例外**:SQLite 是主,文件是镜像。详细理由见 [file-canonical-pattern.md § Review 是例外](file-canonical-pattern.md#review-是例外sqlite-是主file-是镜像)。

## 不能 review 不存在的 card / session

校验阶段:

- `card_id` 不存在 → 404
- `session_id` 不存在 → 400
- `indexes` 解析失败 / 越界 → 400
- 同 `(card_id, session_id, indexes)` 组合已存在 review → 409(防重复)

任一拒绝 → SQLite 不动,事件不写。

## 关于 `indexes` 字段

Review 必须指明"基于这条 session 的哪几个 round"做出判断 —— 这是"反驳/支持的证据"。

`indexes` 语法跟 [`POST /v3/cards`](../../api/v3/cards.md) 的 rounds 字段一致:

- 区间:`"20-25"`
- 列表:`"3,7,12"`

约束:严格单调递增,在 session 范围内。

为什么必须有 indexes:**论坛动力学需要"证据可追溯"**。一条 review 没法只是"我觉得这张卡不对",必须能回到对话里看"哪几轮 round 让你这么觉得"。
