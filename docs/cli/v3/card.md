# card

创建一张 Talk-Card。v2 里 card 是一级命令,**只负责写入**——读取一律通过 `read <card_id>`。

```bash
memory.talk card '<json>' [--json]
```

输入 JSON 结构:

```json
{
  "insight": "选定 LanceDB 做向量存储",
  "rounds": [
    {"session_id": "sess_abc123", "indexes": "11-15"},
    {"session_id": "sess_def456", "indexes": "3,7,12"}
  ],
  "source_cards": [
    {"card_id": "card_01jzaaaa", "relation": "supersedes"},
    {"card_id": "card_01jzbbbb", "relation": "derives_from"}
  ]
}
```

## 字段

- `insight`(必填):一句话认知洞见,也是 embedding 锚点。
- `rounds`:引用列表,每项 `{session_id, indexes}`。`session_id` 必须是 `sess_<...>`。写入者不传原始对话内容,服务端按 `session.rounds[].index` 展开成 `{role, text}` 存入 card。可为空列表——基于多个 card 合成、无原始 session 来源的新 card 属于这种情况。
- `source_cards`(可选):card 之间的关联,**创建时确定,不可修改**。每项 `{card_id, relation}`:
  - `card_id`:被引用 card 必须存在,前缀必须是 `card_<...>`。
  - `relation`:
    - `derives_from`(默认):本卡基于该 card 蒸馏 / 综述而来(高阶 card 引用低阶 card 的典型形态)。
    - `supersedes`:本卡**反驳并替代**该 card(fork 语义)。老 card 不被删,继续在论坛里存在,后续是否真被取代由动力学(review 分布 + 沉浮排序)说了算 —— 没有"立即把老 card 打成 dormant"这种硬切换。
    - 后续可能扩展 `cites` / `merges` 等;未识别 `relation` 报错。
  
  空列表 / 不传等价。同一 `card_id` 允许在 `source_cards` 里以不同 `relation` 多次出现(罕见但不禁止)。

  > **lineage 自然成 DAG**:card 一旦创建不可修改 + `source_cards` 只能引用**创建时已存在**的 card,物理时序就保证 lineage 图是有向无环图,服务端不做环检测。
- `card_id`(可选):不提供则自动生成 `card_<ULID>`。传入时必须是 `card_<...>` 形态。

## indexes 语法

两种形式:

| 形式 | 示例 | 含义 |
|------|------|------|
| 区间 | `"11-15"` | 闭区间 `[11, 15]`,展开为 `11,12,13,14,15` |
| 列表 | `"3,7,12"` | 离散的 index 列表 |

约束(不满足即拒绝整次写入):

- **必须严格单调递增**——`"15-11"` / `"12,7,3"` 报 `indexes must be monotonically increasing`。
- **越界或引用不存在的 index**(包括大于 session `round_count` 或 session 本身不存在)报 `index N out of range for session <session_id>`。
- 同一个 `session_id` 允许在 `rounds` 列表里多次出现(用于跳过中间段);不同 item 之间无顺序约束。

## 输出

### Markdown(默认)

````markdown
ok: created `card_01jz8k2m`
````

错误(到 stderr,exit 1):

````markdown
**error:** index 99 out of range for session `sess_abc123`
````

### JSON(`--json`)

```json
{"status": "ok", "card_id": "card_01jz8k2m"}
```

```json
{"error": "index 99 out of range for session sess_abc123"}
```

返回的 `card_id` 就是**以后所有地方用的读取凭据**——直接喂给 `read` 即可。

## 副作用

- 校验并展开 `rounds` 引用:失败则整条 card 不落库。
- 展开后的每条 round 存为 `{role, text, session_id, index}`——直接把引用信息内联到 round 里。`session_id` 与 `index` 不进向量索引。
- 校验 `source_cards` 里每个 `card_id` 存在、`relation` 合法;失败则整条 card 不落库。
- 自动计算 insight 的 embedding 并写入向量库。
- 在 log 里追加:本 card 的 `created` 事件、每个被引用 session 的 `card_extracted` 事件、每个 `source_cards` 项的 `card_linked` 事件(被引 card 的视角)。
- 本卡 stats 初始化为零(`review_up` / `review_down` / `review_neutral` / `review_count` / `read_count` / `recall_count` 全 0)。后续随 review / read / recall 自动累加,详见 [read](read.md) 的 stats 字段。
