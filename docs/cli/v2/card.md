# card

创建一张 Talk-Card。v2 里 card 是一级命令，**只负责写入**——读取一律通过 `view <result_id>`，而 `result_id` 只能从一次 `search` 拿到。

```bash
memory-talk card '<json>'
```

输入 JSON 结构：

```json
{
  "summary": "选定 LanceDB 做向量存储",
  "rounds": [
    {"session_id": "abc123", "indexes": "11-15"},
    {"session_id": "def456", "indexes": "3,7,12"}
  ]
}
```

## 字段

- `summary`（必填）：一句话认知总结，也是 embedding 锚点。
- `rounds`：引用列表，每项 `{session_id, indexes}`。写入者不传原始对话内容，服务端按 `session.rounds[].index` 展开成 `{role, text}` 存入 card。可为空列表——基于多个 card 合成、无原始 session 来源的新 card 属于这种情况。
- `card_id`（可选）：不提供则自动生成 ULID。

**注意 v2 里 `card` 写入不再接受 `links`**——card → session 的"默认 link"会基于 `rounds` 里出现过的 `session_id` 自动生成（每个不同的 session_id 一条，不带 comment，`ttl = 0` 表示不独立计时、生死跟随 card）。想补 card → card 或其它额外关联用 `link create`（那些是有 TTL 的用户 link）。

## indexes 语法

两种形式：

| 形式 | 示例 | 含义 |
|------|------|------|
| 区间 | `"11-15"` | 闭区间 `[11, 15]`，展开为 `11,12,13,14,15` |
| 列表 | `"3,7,12"` | 离散的 index 列表 |

约束（不满足即拒绝整次写入）：

- **必须严格单调递增**——`"15-11"` / `"12,7,3"` 报 `indexes must be monotonically increasing`。
- **越界或引用不存在的 index**（包括大于 session `round_count` 或 session 本身不存在）报 `index N out of range for session <session_id>`。
- 同一个 `session_id` 允许在 `rounds` 列表里多次出现（用于跳过中间段）；不同 item 之间无顺序约束。

## 输出

```json
{"status": "ok", "card_id": "01jz8k2m..."}
```

返回的 `card_id` 主要用于日志 / 调试里定位这张 card——**不能直接拿去 `link create`**（v2 的 link 只收 result_id）。要读这张 card，或者要把它接到别的对象上，都得先走一次 `search` 让它被索引、拿到 result_id 再操作。

## 副作用

- 校验并展开 `rounds` 引用：失败则整条 card 不落库。
- 展开后的每条 round 存为 `{role, text, session_id, index}`——直接把引用信息内联到 round 里（见 [talk-card.md](../../structure/v2/talk-card.md)）。`session_id` 与 `index` 不进向量索引。
- 为每个出现在 `rounds` 里的不同 `session_id` 自动生成一条 card → session 默认 link（`ttl = 0`）。
- 自动计算 summary 的 embedding 并写入向量库。
