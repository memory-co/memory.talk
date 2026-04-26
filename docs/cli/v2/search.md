# search

v2 主检索入口。hybrid FTS + 向量检索 + 元数据 DSL 过滤,结果分两支返回(cards 和 sessions)。命中的 `card_id` / `session_id` 直接返回给调用方——拿到就能喂给 `view` / `log` / `tag` / `link create`。

```bash
memory-talk search <query> [--where DSL] [--top-k N] [--json]
```

| 参数 | 默认 | 说明 |
|------|------|------|
| `<query>` | — | 检索文本。可为空字符串(配合 `--where` 做纯元数据过滤) |
| `--where`, `-w` | 无 | 元数据过滤 DSL |
| `--top-k` | `settings.search.default_top_k`(默认 10) | 每支(cards / sessions)的上限 |
| `--json` | 关 | 输出 JSON 而非默认 Markdown |

## Markdown(默认)

````markdown
# search: LanceDB 选型

`search_id=sch_01K7XABC`

## cards (2)

### 1. CARD `card_01jz8k2m`

**Summary:** 选定 LanceDB 做向量存储

**Snippets:**

- ...**LanceDB** is a fully managed embedded vector database...
- ...vs Pinecone vs Chroma — **LanceDB** wins for embedded use case...

**Links:**

- FROM `sess_f7a3e1` (session)
- TO `card_01jzp3nq` (card) · 选型后果

### 2. CARD `card_01jzp3nq`

**Summary:** LanceDB 落地后的踩坑清单

**Snippets:**

- ... NFS 上 mmap **LanceDB** 文件 ...

**Links:**

- FROM `sess_8eba9e` (session)

## sessions (1)

### 1. SESSION `sess_187c6576`

**Tags:** `decision`

**Snippets:**

- ...讨论 **LanceDB** 零依赖...
- ...选型决策 **LanceDB** 替代了原本想用的 Pinecone...

**Links:**

- TO `card_01jz8k2m` (card) · 从此对话提取

**Source:** claude-code
````

> **TODO(code):** 当前 `service/cards.py` 里 default link 的方向是 `card → session`(card 是 source、session 是 target),跟本文档示例的 `session → card` 直觉序**相反**。需要把 `service/cards.py::CardService.create()` 里 default link 写入处的 `source/target` 对调,以及对应测试里 `source_type/target_type` 的断言。改完后本文档示例的 `TO/FROM` 不需要再动。

约定:
- 每个结果的标题形如 `### N. CARD \`<card_id>\`` / `### N. SESSION \`<sess_id>\``,大写类型字样 + 反引号包住 id,渲染后类型和 id 都最显眼,不用再扫细节。
- 每个结果下面都用 **加粗 inline 标签**(`**Summary:**` / `**Snippets:**` / `**Links:**` 等)分小节,渲染前后都好读 —— 标签自带分段语义,不依赖颜色和排版。
- card 的元信息是 `Summary`(必有,顶部);session 的"重要元信息"是 `Tags`(顶部),**`Source` 弱信号、放结果末尾**——同一份 corpus 里 Source 大都重复(`claude-code` / `codex` 占绝大多数),扫读时把它放最显眼位置反而干扰。
- `Snippets` 是一个无序列表(`- ...`),每条 snippet 一行。`**...**` 是 highlight 标记,跟 API 返回保持一致。
- `Links` 段是无序列表,从被读对象的视角写方向:
  - `TO \`<id>\` (type) · <comment 若有>` —— 当前对象是 link 的 source(我指向 peer)
  - `FROM \`<id>\` (type) · <comment 若有>` —— 当前对象是 link 的 target(peer 指向我)
  
  Default link 的方向遵循"因果序":session 抽出 card → `source=session, target=card`。所以读 session 时 default link 显示 `TO card_*`(我抽出去的),读 card 时显示 `FROM sess_*`(我从那来)。User-created link 的方向由 `link create` 调用方决定,显示规则同上。
- **TTL 不在 Markdown 输出里**——人类读者关心"还在不在"而不是"还剩几秒",而"在不在"已经由"是否出现"表达了(过期 link 不在 search 结果里;view 里过期 link 在 type 标签上加 `· expired`)。完整 ttl 看 `--json`。
- 链接列表多于 3 条折叠为 `+N more` 单独一行。
- 没有 links 时**整段省略**,不打"*(none)*"占位。
- `score` 不在 Markdown 输出里 —— hybrid RRF 的分数对人类读者价值低,反而干扰扫读。仍然保留在 `--json` 响应里供脚本 / 调试用。
- `links` 行展示前 3 个,超出折叠为 `+N more`。`comment` / `ttl` 仅当存在时显示。`ttl=expired` 表示已过期的用户 link。
- 空命中桶仍然出 header(`## cards (0)`),不打"no results"占位文字。

## JSON(`--json`)

```json
{
  "search_id": "sch_01K7XABC...",
  "query": "LanceDB 选型",
  "cards": {
    "count": 2,
    "results": [
      {
        "card_id": "card_01jz8k2m",
        "rank": 1,
        "score": 0.0312,
        "summary": "选定 LanceDB 做向量存储",
        "snippets": ["...**LanceDB**..."],
        "links": [
          {"link_id": "link_01jzq7rm", "target_id": "sess_f7a3e1", "target_type": "session", "comment": null, "ttl": 0},
          {"link_id": "link_01jzq8sn", "target_id": "card_01jzp3nq", "target_type": "card", "comment": "选型后果", "ttl": 1814400}
        ]
      }
    ]
  },
  "sessions": {
    "count": 1,
    "results": [
      {
        "session_id": "sess_187c6576",
        "rank": 1,
        "score": 0.0289,
        "source": "claude-code",
        "tags": ["decision"],
        "snippets": ["...讨论 **LanceDB** 零依赖..."],
        "links": [
          {"link_id": "link_01jzq9tm", "target_id": "card_01jz8k2m", "target_type": "card", "comment": "从此对话提取", "ttl": 0}
        ]
      }
    ]
  }
}
```

注意：
- 返回体里的 `card_id` / `session_id` / `link_id` 都是**带前缀的裸 id**,直接喂给 `view` / `log` / `link create` 即可,不需要任何中间转换。
- `search_id` 是本次查询的**审计 id**——只出现在服务端 `search_log` 表和 `log` 命令的 detail 里,**不用于任何后续读取**。
- `links` 过滤掉**已过期的用户 link**(`ttl < 0`)——只保留 `ttl >= 0`(默认 link + 活跃用户 link)。想看过期 link 走 `view`。
- search 本身**不续命**任何对象或 link——续命只发生在 `view`。
- `rank` 从 1 开始,对齐 `results` 数组位置。

## 追踪语义

每次 search 都会在服务端 `search_log` 表 + `logs/search/<UTC 日期>.jsonl` 里追加一条——**存的是完整的响应体**(含 `snippets` / `score` / `summary` / `tags` / `links` 等一切呈现给使用者的内容),不是只存命中 id。这样事后审计能完整复原"当时用户看到了什么",即便后续索引变了、对象被改了也能追回原样。详见 [search-result.md](../../structure/v2/search-result.md) 和 [rebuild.md](rebuild.md) 的目录布局。

这是**纯审计**——不做"凭据发行",不参与任何后续调用的校验。想看"这次 AI 会话用了哪些数据"——看 AI 自己的 tool-use 对话记录(sync 之后存成一个 session),那里有每次 `view` / `search` 的输入输出原文。服务端不再造重复的追踪层。

search_log 默认永久保留。老化策略见 `settings.search.search_log_retention_days`。

## DSL

支持字段:`session_id`、`card_id`、`tag`、`source`、`created_at`。运算符:`=`、`!=`、`LIKE`、`IN`、`NOT IN`、`AND`。示例:

```bash
memory-talk search "LanceDB" -w 'tag = "decision" AND source = "claude-code"'
memory-talk search "" -w 'created_at > "2026-04-01"'
memory-talk search "bug" -w 'session_id = "sess_abc123"'
```

DSL 解析失败:

````markdown
**error:** DSL parse error: unknown field 'foo'
````

`--json` 模式下:

```json
{"error": "DSL parse error: unknown field 'foo'"}
```

search 输入 / 输出 / 落库结构的完整定义见 [search-result.md](../../structure/v2/search-result.md)。
