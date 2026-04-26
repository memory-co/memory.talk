# view

按带前缀的 id 读取 card 或 session——**服务端按 id 前缀自动判型**:`card_*` 走 card 读取,`sess_*` 走 session 读取,其它前缀 400。

```bash
memory-talk view <id> [--json]
```

例:

```bash
memory-talk view card_01jz8k2m            # Markdown 默认
memory-talk view sess_187c6576 --json
```

参数：
- `<id>` 必须是 `card_<...>` 或 `sess_<...>`。非法前缀或不存在的 id 返回错误。
- `--json` 输出 JSON。

## Markdown(默认)

### card

````markdown
# CARD `card_01jz8k2m`

**Summary:** 选定 LanceDB 做向量存储

## rounds (2)

1. **[`sess_abc123`#11 human]** ChromaDB vs LanceDB?
2. **[`sess_abc123`#12 assistant]** 推荐 LanceDB 零依赖

## links (3)

- FROM `sess_abc123` (session)
- TO `card_01jzp3nq` (card) · 选型后果——NFS 上踩的坑
- TO `card_01jzold99` (card · expired) · 早期失败的 ChromaDB 方案
````

### session

````markdown
# SESSION `sess_187c6576`

**Created:** `2026-04-10`

**Tags:** `decision`, `project:memory-talk`

**Metadata:**

- project: `/home/user/myapp`

## rounds (2)

1. **[#1 human]** ChromaDB vs LanceDB?
2. **[#2 assistant]** 推荐 LanceDB,零依赖嵌入式

## links (1)

- TO `card_01jz8k2m` (card) · 从此对话提取

---

**Source:** claude-code
````

> **TODO(code):** 当前 `service/cards.py` 里 default link 的方向是 `card → session`,跟本文档示例的 `session → card` 直觉序**相反**。详见 [search.md](search.md) 同款 TODO。

约定:
- 主体内容(`Summary` / `Tags` / `rounds` / `links` 等)放上方;弱信号元信息(session 的 `Source`)用 `---` 分隔后放底部。card 没有 footer 信息,直接没 `---`。`read_at` 在 Markdown 输出里**不展示** —— 人类读者基本不会主动看它,需要时走 `--json`。
- 单条 round 文本太长时,在 80 列宽处截断附 `…`,完整内容看 `--json`。
- 多 ContentBlock 的 round(含 thinking 等非 text 块)用 `+ <type>` 标注:`**[#3 assistant +thinking +tool_use]** ...`。
- `links` 列表里方向以**被读对象的视角**写出:
  - `TO \`<id>\` (type) ...` —— 我是 link 的 source(我指向 peer)
  - `FROM \`<id>\` (type) ...` —— 我是 link 的 target(peer 指向我)
  
  Default link 遵循因果序:session 抽出 card → `source=session, target=card`。所以读 card 时 default link 显示 `FROM sess_*`(我从那来),读 session 时显示 `TO card_*`(我抽出去的)。
- `(type)` 后用 `· expired` 标记已过期的用户 link;**TTL 不在 Markdown 输出里**——人类读者关心"还在不在",由是否出现 + `expired` 标签表达;完整 ttl 数值看 `--json`。
- `(comment)` 仅在有 comment 时显示,作为 `· <comment>` 跟在后面。

## JSON(`--json`)

响应体用 `type` 字段标明本次 view 出的是 card 还是 session,对应主体内容放在同名字段下。

### card

```json
{
  "type": "card",
  "read_at": "2026-04-20T14:32:05Z",
  "card": {
    "card_id": "card_01jz8k2m",
    "summary": "选定 LanceDB 做向量存储",
    "rounds": [
      {"role": "human", "text": "ChromaDB vs LanceDB?", "session_id": "sess_abc123", "index": 11},
      {"role": "assistant", "text": "推荐 LanceDB 零依赖", "session_id": "sess_abc123", "index": 12}
    ],
    "created_at": "2026-04-10T14:30:00Z",
    "ttl": 2419200
  },
  "links": [
    {"link_id": "link_01jzq7rm", "target_id": "sess_abc123", "target_type": "session", "comment": null, "ttl": 0},
    {"link_id": "link_01jzq8sn", "target_id": "card_01jzp3nq", "target_type": "card", "comment": "选型后果——NFS 上踩的坑", "ttl": 1814400},
    {"link_id": "link_01jzq9tm", "target_id": "card_01jzold99", "target_type": "card", "comment": "早期失败的 ChromaDB 方案", "ttl": -86400}
  ]
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
    "tags": ["decision", "project:memory-talk"],
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
  },
  "links": [
    {"link_id": "link_01jzq7rm", "target_id": "card_01jz8k2m", "target_type": "card", "comment": "从此对话提取", "ttl": 1209600}
  ]
}
```

## 要点

- 响应直接暴露**带前缀的裸 id**(`card_id` / `session_id` / `link_id` / `target_id`),拿到就能喂给下一次 `view` / `log` / `link create`。
- `links[].ttl` 三种语义:
  - `= 0`:默认 link(card 写入时自动生成的 card→session)。随 card 一起存在,不独立计时,**不被续命**。
  - `> 0`:活跃的用户 link。view 时按 `ttl.link.factor` **隐式续命**。
  - `< 0`:已过期的用户 link。**仍会返回**(方便看"当初指向过什么"),**不续命**,也不会出现在 `search` 的 link 列表里。
- 本次读取会**隐式刷新被读对象自己的 TTL 以及所有活跃用户 link 的 TTL**(`ttl > 0` 的那些)——默认 link 和已过期 link 都不参与续命。
- Session 的 rounds 一次性全部返回,不支持窗口参数。若 session 过长,在 search 侧用更精准的 `query` / `--where` 缩小命中。

Round / ContentBlock 结构见 [session.md](../../structure/v2/session.md),Card 结构见 [talk-card.md](../../structure/v2/talk-card.md)。

## 副作用

- view card 时,**刷新 card 自身的 TTL**(按 `ttl.card.factor`)。view session 时不刷新——session 本身没有 TTL,是永久对象。
- 两种场景都**隐式刷新活跃用户 link** 的 TTL(`ttl > 0`,按 `ttl.link.factor`)。默认 link(`ttl=0`)和已过期 link(`ttl<0`)不参与。
