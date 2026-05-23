# read

按带前缀的 id 读取 card 或 session——**服务端按 id 前缀自动判型**:`card_*` 走 card 读取,`sess_*` 走 session 读取,其它前缀 400。

```bash
memory-talk read <id> [--json]
memory-talk --no-pager read <id>          # 强制直出
```

例:

```bash
memory-talk read card_01jz8k2m            # Markdown 默认,长输出走 pager
memory-talk read sess_187c6576 --json     # JSON,永远不 pager
memory-talk read sess_187c6576 | less     # 显式 pipe,不 pager
```

参数：
- `<id>` 必须是 `card_<...>` 或 `sess_<...>`。非法前缀或不存在的 id 返回错误。
- `--json` 输出 JSON。

### Pager 行为

`read` 是目前**唯一**进 pager 的命令(其它命令暂不开启 —— 跟 git 只让 `log` / `diff` / `show` 进 pager 一个套路)。具体规则:

| 条件 | 行为 |
|---|---|
| 交互终端(stdout + stdin 都是 TTY) | 自动走 pager(`$PAGER`,默认 `less -RFX`),可滚动 / 搜索 / `q` 退出 |
| 输出比一屏短 | `less -F` 自动退,不打扰 |
| 管道 / 重定向 / subprocess 调用 / AI tool 调用 | 直出,无 pager,无 ANSI 颜色(rich 自动剥) |
| `--json` | 永远直出 |
| `--no-pager`(顶层 flag)或 `NO_PAGER=1` 环境变量 | 强制直出 |

AI 工具 / 脚本 / shell pipe 调用 `memory-talk read xxx` 行为跟以前**完全一致**,只有人在终端里敲才会进入交互滚动。

## Markdown(默认)

### card

````markdown
# CARD `card_01jz8k2m`

**Insight:** 选定 LanceDB 做向量存储

**Stats:** ↑1 ↓1 · reviews 3 · reads 8 · recalls 4

**From:**

- `supersedes` → `card_01jzaaaa`
- `derives_from` → `card_01jzbbbb`

## reviews (3)

- **+1** `sess_abc123` #20-25 — 再次确认 LanceDB 选型,生产跑了 3 个月稳定
- **-1** `sess_def456` #5,8 — 原以为 mmap NFS 没事,生产撞了 inode lock 的坑
- **0** `sess_xyz789` #11 — 又讨论到了,没改变结论

## rounds (2)

**[`sess_abc123`#11 human]**

ChromaDB vs LanceDB?

---

**[`sess_abc123`#12 assistant]**

推荐 **LanceDB**:

- 零依赖、嵌入式
- 自带 FTS,跟向量混合检索

```python
# 伪代码
db = lancedb.connect("./data")
```
````

### session

````markdown
# SESSION `sess_187c6576`

**Created:** `2026-04-10`

**Metadata:**

- project: `/home/user/myapp`

**Source:** claude-code

## rounds (2)

**[#1 human]**

ChromaDB vs LanceDB?

---

**[#2 assistant]**

推荐 LanceDB,零依赖嵌入式。
````

约定:
- 顺序固定:**头部元数据**(`Insight` / `Stats` / `From` 或 `Created` / `Metadata` / `Source`)→ **`## reviews`**(card 独有,无 review 时省略)→ **`## rounds`**。每段元数据之间用空行隔开;rounds 是最后一段,后面没有 footer。session 的 `Source` 跟其它元数据并排放头部(放最末尾会被长 rounds 推得看不见)。
- `**Stats:**` 仅 card 有,inline 单行:`↑<review_up> ↓<review_down> · reviews <review_count> · reads <read_count> · recalls <recall_count>`。这是 card 当前在论坛里的位置信号 —— 真讨论(`reviews` / `↑↓`)和路过(`reads` / `recalls`)分两类显示。
- `**From:**` 仅 card 有,展示 `source_cards`,每条形如 `\`<relation>\` → \`<card_id>\``;无 `source_cards` 时**整段省略**。`relation` 加反引号是为了让 `supersedes` / `derives_from` 这种非自然词更容易被扫到。
- `## reviews` 仅 card 有,按 `created_at` 倒序排列,标题里只附数量 `(N)`(净得分 / 分布看上面 `Stats:` 行,不重复)。每条形如 `**±N** \`<sess_id>\` #<indexes> — <comment>`;`score=0` 时显示 `**0**`;`comment` 缺失时省略破折号那一段。无 review 时**整段省略**。新增 review 走 [review](review.md)。
- `## rounds` 放最后,因为单条 round 的内容里**经常本身就是 Markdown**(代码块、列表、引用、子标题等),放在中间会跟外层结构混在一起难读。挪到最后等于"先看元数据,再看内容正文"。
- 每个 round 之间用 `---` 分隔。round 内部:第一行是 `**[<round 头>]**`(card:`[\`<sess_id>\`#<idx> <role>]`;session:`[#<idx> <role>]`),空一行后是 round 正文(原样输出 content 文本,可以含任意 Markdown)。
- 多 ContentBlock 的 round(含 thinking 等非 text 块)用 `+ <type>` 标注:`**[#3 assistant +thinking +tool_use]**`。正文里只渲染 text/code 块的内容,其他类型的存在用头部 `+xxx` 标记表示。
- 单条 round 正文不再做 80 列截断 —— round 本身可以是长篇内容,放在最后也不会挤占元数据视野。完整 raw 内容仍在 `--json` 里。
- `read_at` 在 Markdown 输出里**不展示** —— 人类读者基本不会主动看它,需要时走 `--json`。

## JSON(`--json`)

响应体用 `type` 字段标明本次 read 出的是 card 还是 session,对应主体内容放在同名字段下。

### card

```json
{
  "type": "card",
  "read_at": "2026-04-20T14:32:05Z",
  "card": {
    "card_id": "card_01jz8k2m",
    "insight": "选定 LanceDB 做向量存储",
    "source_cards": [
      {"card_id": "card_01jzaaaa", "relation": "supersedes"},
      {"card_id": "card_01jzbbbb", "relation": "derives_from"}
    ],
    "rounds": [
      {"role": "human", "text": "ChromaDB vs LanceDB?", "session_id": "sess_abc123", "index": 11},
      {"role": "assistant", "text": "推荐 LanceDB 零依赖", "session_id": "sess_abc123", "index": 12}
    ],
    "reviews": [
      {"review_id": "review_01jzr5kq", "session_id": "sess_abc123", "indexes": "20-25", "score": 1, "comment": "再次确认 LanceDB 选型,生产跑了 3 个月稳定", "created_at": "2026-05-01T09:14:22Z"},
      {"review_id": "review_01jzs7mp", "session_id": "sess_def456", "indexes": "5,8", "score": -1, "comment": "原以为 mmap NFS 没事,生产撞了 inode lock 的坑", "created_at": "2026-04-22T18:03:11Z"},
      {"review_id": "review_01jzq3kn", "session_id": "sess_xyz789", "indexes": "11", "score": 0, "comment": "又讨论到了,没改变结论", "created_at": "2026-04-15T12:48:00Z"}
    ],
    "stats": {
      "review_up": 1,
      "review_down": 1,
      "review_neutral": 1,
      "review_count": 3,
      "read_count": 8,
      "recall_count": 4
    },
    "created_at": "2026-04-10T14:30:00Z"
  }
}
```

### session

```json
{
  "type": "session",
  "read_at": "2026-04-20T14:32:05Z",
  "session": {
    "session_id": "sess_187c6576",
    "source": "claude-code",
    "created_at": "2026-04-10T14:30:00Z",
    "metadata": {"project": "/home/user/myapp"},
    "rounds": [
      {
        "index": 1,
        "round_id": "r001",
        "speaker": "user",
        "role": "human",
        "content": [{"type": "text", "text": "ChromaDB vs LanceDB?"}]
      },
      {
        "index": 2,
        "round_id": "r002",
        "speaker": "assistant",
        "role": "assistant",
        "content": [{"type": "text", "text": "推荐 LanceDB,零依赖嵌入式"}]
      }
    ]
  }
}
```

## 要点

- 响应直接暴露**带前缀的裸 id**(`card_id` / `session_id`),拿到就能喂给下一次 `read`。
- read card **不修改 card 内容** —— `insight` / `rounds` / `source_cards` 不可改。但会**累加 `card.stats.read_count`**(每次 read 一次 +1) —— 这是论坛"被路过"的活跃度信号,跟 review 的"真讨论"信号分两类(详见上面 `Stats:` 行)。
- read session 完全只读,不更新任何 stats(session 不参与 card 论坛动力学)。
- `card.reviews` 是按 `created_at` 倒序的快照;新增 review 走 [review](review.md)。
- Session 的 rounds 一次性全部返回,不支持窗口参数。若 session 过长,在 search 侧用更精准的 `query` / `--where` 缩小命中。

