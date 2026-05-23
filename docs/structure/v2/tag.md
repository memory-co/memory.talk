# Tag

Tag 是挂在 **session** 或 **card** 上的 **key + value** 标注。它**不是**独立实体——没有 `tag_id`，没有自己的生命周期，只作为某个 subject 的"附属属性"存在。

## 形态

每个 subject 上的 tags 是一个**有序的 key→value 映射**（dict）。同一 subject 上 key 唯一，后写覆盖前写。

```json
{
  "project": "memory.talk",
  "decision": "",
  "owner": "alice",
  "path": "/etc/hosts:rw"
}
```

字段释义：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| key | string | 是 | 标签名。strip 后非空。同一 subject 内唯一 |
| value | string | 否 | 标签值。`""` 表示"只标 key"（如 `decision`） |

## 字符串语法（`key:value`）

API 和 CLI 在传入时都用一个字符串 `"key:value"` 表示一对 tag：

| 输入 | 解析为 |
|---|---|
| `project:memory.talk` | `(project, memory.talk)` |
| `decision` | `(decision, "")` |
| `version:` | `(version, "")` |
| `path:/etc/hosts:rw` | `(path, /etc/hosts:rw)`（按**首个** `:` 分割，value 内允许 `:`）|

规则：

- 按**首个** `:` 分割，所以 value 里 `:` 任意出现。
- 不带 `:` → value 为空字符串。
- key / value 各自 `strip()` 去首尾空白。
- key 不能为空（`""` / `":foo"` / `":"` / `"   :foo"` 都拒绝）。

## 作用对象

| Subject | ID 前缀 | 存储位置 |
|---|---|---|
| session | `sess_` | `sessions/{source}/{id[0:2]}/{session_id}/meta.json` 的 `tags` 字段（也镜像到 sqlite `sessions.tags` 列）|
| card | `card_` | sqlite `cards.tags` 列 |

**session 和 card 的 tag 集合互相独立**——给 `sess_x` 加 `project:foo` 不会传染到任何 card，反之亦然。Session 与其包含 round 衍生出的 card 之间**没有任何 tag 继承关系**。

## 不参与检索

> **管理型标签，不进入索引。**
>
> - search 的 BM25 + 向量索引来源于 round 内容和 card summary，**不读 tag 字段**。
> - recall 命中候选不会因 tag 匹配而被加权或召回。
> - 改 tag **不会触发 rebuild**——tag 数据从未进入 FTS / 向量索引。
>
> 想做"按 tag 过滤"的用例（如"只看 `project:foo` 的 session"）请走未来的 `list` / `filter` 类元数据查询接口，不要试图通过 search/recall 实现。

设计意图：tag 是给**人/工具**用的"标注 / 分类 / 状态位"，不是给**模型**用的语义信号。让 tag 进检索会让用户产生"加了 tag 就能召回到"的错觉，这是个 footgun。

## 没有 TTL，不参与遗忘

card 和 link 有 TTL（自然遗忘），**tag 没有**：

- tag 只在显式 `DELETE` 时才消失。
- subject 自身被删（card 过期清理 / session 主动删）时，tag 跟着一起消失。
- tag 不被 view 续命（也无意义——它没倒计时）。

## 生命周期事件

每次 tag 变更在所属 subject 上产生一条 event（事件本身落到 subject 的 event log，跟 `card_created` / `session_synced` 等是同一通道）：

| event kind | payload | 触发时机 |
|---|---|---|
| `tag_added` | `{"key": "...", "value": "..."}` | POST 请求里**新引入**一个 key |
| `tag_updated` | `{"key": "...", "value": "<新>", "prior_value": "<旧>"}` | POST 请求**改写**了已有 key 的 value |
| `tag_removed` | `{"key": "...", "value": "<删前 value>"}` | DELETE 请求**真正**删除了一个存在的 key |

**幂等请求不发事件**（POST 同 key 同 value、DELETE 不存在的 key）。

## 跟 link 的区别

容易把两者搞混，对比一下：

| 维度 | Tag | Link |
|---|---|---|
| 是不是独立实体 | 否（subject 的属性） | 是（有 `link_id`、自己的 schema） |
| 多对多 | 一个 subject 多 tag，一个 tag key 也可能挂多个 subject | 一条 link 严格连接 1 source + 1 target |
| 有没有 TTL | 无 | 有（默认 link 跟随 parent，用户 link 独立计时） |
| 有没有 ID | 无 | 有（`link_<ULID>`） |
| 进不进 view 输出 | 是（作为 subject 的字段一部分） | 是（作为 card.links / 独立查询）|
| 进不进检索 | **不进** | 不直接进，但可以用 link 关系做"间接召回"（v2 暂未启用）|

**直觉对照**：tag 是**一张便签贴在物体上**；link 是**两个物体之间拉一条绳子**。

## 操作接口

完整 API 见 [`docs/api/v2/tags.md`](../../api/v2/tags.md)。简表：

| 操作 | 端点 |
|---|---|
| Add / Update tags on a session | `POST /v2/sessions/{session_id}/tags` |
| Remove tags from a session | `DELETE /v2/sessions/{session_id}/tags?key=...&key=...` |
| Add / Update tags on a card | `POST /v2/cards/{card_id}/tags` |
| Remove tags from a card | `DELETE /v2/cards/{card_id}/tags?key=...&key=...` |

POST 是 upsert 语义：key 不存在 → 加；key 已存在但 value 不同 → 改；key 已存在且 value 相同 → noop。要改某个 tag 的 value 直接 POST 同名 key 带新 value 即可，没有专门的 `update` 接口。

DELETE 走 query string 数组（`?key=a&key=b`），无 body，按 key 移除（请求里 value 部分被忽略）。
