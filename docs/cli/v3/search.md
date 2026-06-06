# search

v3 主检索入口。hybrid FTS + 向量 + 元数据 / stats DSL 过滤,**card 和 session 在同一个沉浮公式下融合排序** —— 返回单一结果流,按 final score 降序;card 像精炼洞见,session 像对话原文,谁在前由公式说了算。session 内部按 round 行级召回,多 round 命中聚合到同一 session 块,每个命中给前后一行上下文窗。

命中的 `card_id` / `session_id` 直接返回给调用方 —— 拿到就能喂给 `read`。

```bash
memory.talk search <query> [--where DSL] [--top-k N] [--recall [--session SID]] [--json]
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `<query>` | — | 检索文本。可为空字符串(配合 `--where` 做纯元数据 / stats 过滤) |
| `--where`, `-w` | 无 | 元数据 / stats / type 过滤 DSL,见 [`../../works/v3/dsl.md`](../../works/v3/dsl.md) |
| `--top-k` | `settings.search.default_top_k`(默认 10) | **总**结果数上限(card + session 合计) |
| `--recall` | 关 | 切换到 recall 视角(cards-only,裸 RRF) |
| `--session` | 无 | 仅 `--recall` 下生效,模拟该 session 的 dedup |
| `--json` | 关 | 输出 JSON 而非默认 Markdown |

排序公式 / `--recall` 调试视角 / DSL 语法见 [`../../works/v3/search-ranking.md`](../../works/v3/search-ranking.md) 和 [`../../works/v3/dsl.md`](../../works/v3/dsl.md)。

### Pager 行为

0.8.x 起 `search` 跟 [`read`](read.md) 同款进 pager:交互终端下输出自动走 `$PAGER`(默认 `less -RFX`),可滚动 / 搜索 / `q` 退出。`--json` / 管道 / subprocess / AI tool 调用 / `--no-pager` / `NO_PAGER=1` 一律直出 —— 详细矩阵见 [`read.md#pager-行为`](read.md#pager-行为)。

## Markdown(默认)

`````markdown
# search: LanceDB 选型

`search_id=sch_01K7XABC` · 4 results

---

### [CARD] `card_01jz8k2m` · `↑7 ↓3 · reviews 12 · reads 42 · recalls 18` · 2026-04-10 22:30 (43 days ago)

选定 **LanceDB** 做向量存储,主要因为零依赖嵌入式架构

---

### [SESSION] `sess_187c6576` · claude-code · 3 hits

**#11, #13** · top score `0.0163` · 2026-04-10 22:32 (43 days ago)
````
[10 AI] 我们要选个向量库, 纠结
[11 HUMAN*] 我看 LanceDB 是个不错的选择, 零依赖
[12 AI] 好的, 那就 LanceDB 了
[13 AI*] 嵌入式部署最方便, LanceDB 跟应用一起走
[14 HUMAN] OK 就这么定
````

---

### [CARD] `card_01jzp3nq` · `↑2 ↓0 · reviews 2 · reads 5 · recalls 1` · 2026-05-01 17:14 (22 days ago)

LanceDB 落地后的踩坑清单
`````

### 约定

- **单一结果流**,按 final score 降序混排 card 和 session。**没有**"## cards"/"## sessions"分组。
- 顶部一行 `search_id=... · N results`。
- 每个 result 都是 H3 标题 `### [TYPE] \`<id>\` · <metadata>`,中间用 `---` 分隔。
- Card 块:`[CARD] \`<card_id>\` · \`<stats inline>\``,下方整段 `insight` + 关键词 `**...**` 内联高亮。
- Session 块:`[SESSION] \`<sess_id>\` · <source> · K hits`,每个命中(或合并相邻命中)一个 fenced code block,按 idx 升序逐行 `[<idx> <ROLE>[*]] <text>`(`*` 标主 hit)。
- **上下文窗**:前 1 行 + 后 1 行,固定不可调;相邻 hit `idx` 差 `≤ 2` 自动合并到同一 fence(每 round 只画一次)。
- 每个 session 最多 3 个 hit 块。
- `score` 在 Markdown 输出里露出。这是 LanceDB RRF 融合分,典型 `0.01–0.03`,**只看排名不看绝对相似度**,详见 [`../../structure/v3/search-result.md#关于-rrf-分的一句忠告`](../../structure/v3/search-result.md#关于-rrf-分的一句忠告)。
- 0 命中 → header 仍然出,不打"no results"占位。

## JSON(`--json`)

```json
{
  "search_id": "sch_01K7XABC...",
  "query": "LanceDB 选型",
  "count": 4,
  "results": [
    {
      "type": "card",
      "rank": 1,
      "score": 0.52,
      "card_id": "card_01jz8k2m",
      "insight": "选定 **LanceDB** 做向量存储,主要因为零依赖嵌入式架构",
      "stats": {
        "review_up": 7, "review_down": 3, "review_neutral": 2,
        "review_count": 12, "read_count": 42, "recall_count": 18
      }
    },
    {
      "type": "session",
      "rank": 2,
      "score": 0.42,
      "session_id": "sess_187c6576",
      "source": "claude-code",
      "hit_count": 8,
      "hits_shown": 3,
      "hits": [
        {
          "index": 11,
          "role": "human",
          "text": "我看 **LanceDB** 是个不错的选择,零依赖",
          "score": 0.38,
          "context_before": {"index": 10, "role": "human", "text": "我们要选个向量库,纠结"},
          "context_after": {"index": 12, "role": "assistant", "text": "好的,那就 LanceDB 了"}
        }
      ]
    }
  ]
}
```

字段表见 [`../../api/v3/search.md`](../../api/v3/search.md)。

## DSL `-w`

```bash
memory.talk search "LanceDB" -w 'source = "claude-code"'
memory.talk search "" -w 'read_count > 10 AND review_count = 0'
memory.talk search "LanceDB" -w 'type = "card"'
```

完整字段 / 运算符 / 示例见 [`../../works/v3/dsl.md`](../../works/v3/dsl.md)。

## 错误

| 情况 | 行为 |
|---|---|
| `--session` 单独用(不带 `--recall`) | exit 2 |
| DSL 解析失败 | exit 1,打 `error: DSL parse error: ...` |
| query 缺失 | exit 2 |
| server 不可达 | exit 1 |
