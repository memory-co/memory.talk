# Card-Links API

card↔card 的 **IBIS 边**——嵌在卡下(跟 `positions` 同构:`/v4/cards/{card_id}/...`)。`card_id`(主体卡,边的 from 端)在路径里。

CLI 对应 [`card link`](../../cli/v4/link.md)(`card link create` / `card link list`)。字段语义详见 [`../../structure/v4/card-link.md`](../../structure/v4/card-link.md)。

> SQLite 表名仍是 `card_links`(只是 API 路径嵌到卡下);Position 之间不直接结网,边只在卡↔卡层。

---

## POST /v4/cards/{card_id}/links

给 `{card_id}`(主体卡)建一条出边。

### 请求体

```json
{
  "type": "specializes",
  "target_id": "card_01jzaaaa"
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `type` | 是 | 边类型,见下表 |
| `target_id` | 是 | 对端:多为 `card_<...>`;`suggested_by` 可指 `pos_<...>`(前缀自带类型,免 `target_type` 列) |

(主体卡 = 路径里的 `{card_id}`,边非对称,主体在前。)

### `type` 取值

| 值 | 含义 | 方向 |
|---|---|---|
| `specializes` | 主体是对端的更窄版(子问题,**DAG 非树**) | 有向 |
| `suggested_by` | 主体被对端引出来(出处 / 因果);对端**可为 Position** | 有向 |
| `questions` | 主体质疑对端的前提 / 框架 | 有向 |
| `replaces` | 主体重述并取代对端(**保留历史**,不删对端) | 有向 |
| `related` | 兜底泛关联 | 无向 |

> `replaces`(issue 层:一个**问题**重述取代另一个问题)跟 Position 层的 `forked_from_position_id`(同一问题下一个**答案**分叉自另一个答案)是两个不同机制,别混。

### 多值 + 去重

- **五类型全多值**:同一 `(card_id, type)` 下可挂多条(如 `specializes` 多父)。主键 `(card_id, type, target_id)`。
- `related` 无向:写时规范化排序(小 id 在前),只存一遍,避免 A→B 和 B→A 重复。
- 重复 `(card_id, type, target_id)` → 幂等(不报错,不新增)。

### 响应

```json
{"status": "ok", "card_id": "card_01jz8k2m", "type": "specializes", "target_id": "card_01jzaaaa"}
```

### 副作用

- 校验路径 `card_id` 存在、`type` 在白名单、`target_id` 前缀合法(`card_` 或 `pos_`)→ 失败不落库。
- 写一行 `card_links`(SQLite 派生运行态)。
- **不校验 `target_id` 是否存在**:SQLite 是派生索引,容忍悬挂引用、**从不加 FOREIGN KEY**(target 可能后到 / 已删,图层照样成立)。

### 错误

| 情况 | 状态 / 消息 |
|---|---|
| 路径 `card_id` 不存在 | 404, `card <cid> not found` |
| `type` 不在白名单 | 400, `unknown link type: <value>` |
| `target_id` 前缀既不是 `card_` 也不是 `pos_` | 400, `invalid target_id prefix` |

> IBIS 关系集**不完备**,后续可按需补 `depends_on` / `part_of`——加 `type` 白名单即可,表结构不变。

---

## GET /v4/cards/{card_id}/links

列这张卡相关的边:它**指出去的**(本卡为主体)+ **指过来的**(别的卡指本卡)。

### 响应

```json
{
  "card_id": "card_01jz8k2m",
  "out": [{"type": "specializes", "target_id": "card_01jzsub"}],
  "in":  [{"type": "replaces", "from_card_id": "card_01jzold"}]
}
```

- `out` = 主体是本卡的边;`in` = `target_id` 指向本卡的边(反查,`from_card_id` 是那条边的主体)。

### 错误

| 情况 | 状态 |
|---|---|
| 路径 `card_id` 不存在 | 404 |
