# Card-Links API

card↔card 的 **IBIS 边**——嵌在卡下(跟 `positions` 同构:`/v4/cards/{card_id}/...`)。`card_id`(主体卡,边的 from 端)在路径里。

一条边是**受治理对象**(跟 Position 平行):有 `claim`(为什么成立)、顶踩计数、**现算 credence**、证据出处(`link_sessions`)、append-only,可被 review。寻址 `<card_id>#l<n>`。

CLI 对应 [`card link`](../../cli/v4/card.md#card-link)(直接建边,无 list——看一张卡的边走 [`read`](read.md))。字段语义详见 [`../../structure/v4/card-link.md`](../../structure/v4/card-link.md)。

> SQLite 表名仍是 `card_links`(只是 API 路径嵌到卡下);Position 之间不直接结网,边只在卡↔卡层。
>
> **存在即合理 vs 择优**:Link credence 给**每条边定去留**(过阈值才显示,边不互相竞争);Position credence 给**答案排座次**(择优,选当下答案)。详见 [card-link.md](../../structure/v4/card-link.md) 顶部。

---

## POST /v4/cards/{card_id}/links

给 `{card_id}`(主体卡)建一条出边。

### 请求体

```json
{
  "type": "specializes",
  "target_id": "card_01jzaaaa",
  "claim": "本卡是它的一个特例 —— 都走同一套 auth,只是把范围收窄到 OAuth 回调这一段。",
  "source": ["sess_def456:30-34"]
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `type` | 是 | 边类型,见下表 |
| `target_id` | 是 | 对端 id:多为 `card_<...>`;`suggested_by` 可指某卡的答案 `card_<...>#p<n>`(Position 无独立 id,寻址 `card_id#p<n>`)。服务端据 `#p` 分片派生并落 `target_type`(`card` / `position`)列,便于按对端类型过滤 |
| `claim` | **是** | **这条边为什么成立**(关系断言 / 理由)。内联在边上、create 即冻(append-only,跟 Position 的 `claim` 同构) |
| `source` | 否 | 边的出处,`<session_id>:<indexes>` 数组(可多 session),每个落一条 `link_sessions`(这条边从哪几轮观察出来) |

(主体卡 = 路径里的 `{card_id}`,边非对称,主体在前。)

### `type` 取值

| 值 | 含义 | 方向 |
|---|---|---|
| `specializes` | 主体是对端的更窄版(子问题,**DAG 非树**) | 有向 |
| `suggested_by` | 主体被对端引出来(出处 / 因果);对端**可为 Position** | 有向 |
| `questions` | 主体质疑对端的前提 / 框架 | 有向 |
| `replaces` | 主体重述并取代对端(**保留历史**,不删对端) | 有向 |
| `related` | 兜底泛关联 | 无向 |

> `replaces`(issue 层:一个**问题**重述取代另一个问题)跟 Position 层的 `forked_from`(同一问题下一个**答案**分叉自另一个答案)是两个不同机制,别混。

### 多值 + 不重边

- **五类型全多值(存在即合理)**:同一 `(card_id, type)` 下可挂多条(如 `specializes` 多父;主体同时特化 B 和 C 合法),各边各自成立、不竞争。
- `related` 无向:写时规范化排序(小 id 在前),只存一遍,避免 A→B 和 B→A 重复。
- **不重边**:UNIQUE `(card_id, type, target_id)` → 重复该三元组报 409(改主意是踩它 / 加反向边,不是再建同边)。`link`(`l<n>`)是这条边的卡内地址。

### 响应

```json
{"status": "ok", "card_id": "card_01jz8k2m", "link": "l1", "type": "specializes", "target_id": "card_01jzaaaa", "target_type": "card"}
```

`link` = 这条边的卡内序号 `l<n>`(以后 review / read 的寻址 `card_01jz8k2m#l1`)。

### 副作用

- 校验路径 `card_id` 存在、`type` 在白名单、`target_id` 合法(`card_<...>`,或带 `#p<n>` 分片的 `card_<...>#p<n>`)、`claim` 非空、不违反 UNIQUE → 失败不落库;据有无 `#p` 分片落 `target_type`(`card` / `position`)列。
- 写一行 `card_links`(SQLite 派生运行态:`up/down/neutral_count` 初始化 0,**不算 credence**)+ `links/l<n>.json`(canonical:`type` + `target_id` + `claim` + `created_at`,边核不可变)+ 每个 `source` 落一条 `link_sessions` + `cards.link_count++`。
- **不校验 `target_id` 是否存在**:SQLite 是派生索引,容忍悬挂引用、**从不加 FOREIGN KEY**(target 可能后到 / 已删,图层照样成立)。

### 错误

| 情况 | 状态 / 消息 |
|---|---|
| 路径 `card_id` 不存在 | 404, `card <cid> not found` |
| `type` 不在白名单 | 400, `unknown link type: <value>` |
| `target_id` 既不是 `card_<...>` 也不是 `card_<...>#p<n>` | 400, `invalid target_id` |
| `claim` 缺失 / 空 | 400, `claim required` |
| `source` 的 `indexes` 越界 / 非单调 | 400, `indexes must be monotonically increasing` / `index N out of range` |
| 同边已存在(违反 UNIQUE `(card_id, type, target_id)`) | 409, `link already exists` |

> IBIS 关系集**不完备**,后续可按需补 `depends_on` / `part_of`——加 `type` 白名单即可,表结构不变。

---

## POST /v4/cards/{card_id}/links/{link}/reviews

对一条 **CardLink** 写一条 review(「表态」):带 `argument`(+1 这条边成立 / 0 中立 / −1 不成立)+ comment + 来自某次 session 的证据 rounds。**跟 [`POST /v4/cards/{cid}/positions/{p}/reviews`](reviews.md) 平行**——只是 target 从 Position(`{position}` = `p<n>`)换成 Link(`{link}` = `l<n>`)。append-only,创建即冻结。

`{link}` = 卡内序号 `l<n>`(Link 无独立 id,寻址 `<card_id>#l<n>`,路径里拆成 `{card_id}` + `{link}`)。服务端从 `#l` 分片派生 `target_kind=link`。

CLI 对应 [`card review --target card_xxx#l<n>`](../../cli/v4/card.md#card-review)。字段 / 错误 / 唯一性语义与 positions 版完全一致,见 [reviews.md](reviews.md)。

### 请求体

```json
{
  "session_id": "sess_def456",
  "indexes": "30-34",
  "argument": 1,
  "comment": "这条 specializes 边确实成立——两卡都走同一套 auth"
}
```

### 响应

```json
{
  "status": "ok",
  "review_id": "review_01jzr5kq",
  "card_id": "card_01jz8k2m",
  "target": "l1",
  "target_kind": "link",
  "session_id": "sess_def456",
  "argument": 1
}
```

### 副作用

- 校验:`card_id` 存在 + 卡内有 `link`(`l<n>`)+ `session_id` 存在 + `indexes` 不越界 + `argument ∈ {-1,0,1}` → 任一失败整条不落库。
- **累加被表态 Link 的计数**(原子 upsert):`+1`→`up_count++` / `-1`→`down_count++` / `0`→`neutral_count++`(落 `card_links`)。
- **不动 `credence`** —— 不是存储字段,read / 过滤时按 `up−down`(或 Wilson)现算;credence 决定这条边显不显示(存在即合理,不与同类型其它边竞争)。
- 落 `reviews` 表(`target=l<n>`、`target_kind=link`),沿用 v3 review canonical;不进向量索引。

---

## GET（看边走 read,无单独列边端点)

**没有单独的「列边」端点**——看一张卡的边(out / in 两向)走 [`POST /v4/read`](read.md) `{id: card_…}`,响应里带 `links`(各带 `claim` + 顶踩计数 + **现算 credence**;低于阈值的边淡出);读单条边走 `POST /v4/read {id: "card_…#l<n>"}`(按 `#l` 分片判型,返回这条边 + 它收到的全部 review,跟读单个 Position 同构)。`credence` 是响应里**现算**的派生值,不在存储里。
