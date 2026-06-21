# Session Marks API

逐 round 打注解的写入端点。**一次提交 = 一份 mark**(标整个 session);服务端**自动分配** mark id `m<n>`(第一遍 `m1`、第二遍 `m2`…,用户不填)。每条 round 的 `comment` 里 `#…？` 自动建卡 / 关联老卡,出处落 [`card_sessions`](../../structure/v4/card-session.md)。机制见 [`../../works/v4/session-mark.md`](../../works/v4/session-mark.md),数据结构见 [`../../structure/v4/session-mark.md`](../../structure/v4/session-mark.md),CLI 见 [`../../cli/v4/session.md#session-mark`](../../cli/v4/session.md#session-mark)。

```
Submit   POST    /v4/sessions/{session_id}/marks      提交一份 mark(乐观锁 last_index;服务端配 m<n>)
List     GET     /v4/sessions/{session_id}/marks      列这个 session 的所有 mark(元信息)
Clear    DELETE  /v4/sessions/{session_id}/marks      清空这个 session 的所有 mark(+ 出处边)
```

> 查看一条 session 的 mark 走 **session 读取**:[`read sess_…`](read.md#响应--sess_) 把这条 session 的 `marks[]` 折进 session 响应里(rounds + marks 一起返回),单条 mark 的全文走 [`read sess_…#m1`](read.md#响应--sess_mn单条-mark)分片读。**没有单独的 mark 列表命令**——下方 `GET …/marks` 仍在(元信息),但不是面向用户的列表入口。反查「这条 mark 启发了哪些卡」走 [`GET /v4/sessions/{session_id}/cards`](sessions.md#get-v4sessionssession_idcards)。

## POST /v4/sessions/{session_id}/marks

提交一份 mark。**乐观锁**:`last_index` 与 session 当前最新 round index 不一致 → 整份拒绝(409)。mark id `m<n>` **由服务端自动分配**(`next_seq` = COUNT+1):提交体里**不带** id。

**round 校验**(整份拒绝 → 400,**在任何写入之前**):

- 首条 `index` 必须是 `1`(从 session 第一轮开始读;从中间起 = 偷跳 → 拒绝);
- `index` 严格递增、不重复、每个落在 `[1, last_index]`;
- **覆盖率(以写代读)**:distinct `index` 数 ≥ `ceil(0.9 × last_index)`。不够 → 整份拒绝,消息形如 `coverage 23% (12/52 rounds) < 90%`。阈值常量 `MARK_COVERAGE_THRESHOLD = 0.9`。

### 请求体

```json
{
  "last_index": 41,
  "description": "在配 pty、用户突然提 tmux 的那几轮——想搞清他到底要什么",
  "rounds": [
    {"index": 1},
    {"index": 2, "comment": "用户要给 pty 配上终端。"},
    {"index": 37, "comment": "配 pty 时用户突然提了 tmux。#为什么 pty 会让用户想到 tmux？"},
    {"index": 38, "issues": [{"issue": "可重连会话是不是真需求", "indexes": "37-38"}]}
  ]
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `last_index` | 是 | 提交时读到的 session 最新 round index(乐观锁基线 / 总 round 数) |
| `description` | 是 | 这次标注的场景;落进 mark 文件 |
| `rounds[]` | 是 | 非空数组,每条 `{index, comment?, issues?}`;从 `index: 1` 起严格递增,覆盖 ≥90% |
| `rounds[].index` | 是 | 这条标注指向第几轮(1-indexed)。首条必须 `1` |
| `rounds[].comment` | 否 | 这一轮的感悟。其中 `#…？`(`#` 起、`？`/`?` 止)自动解析成 issue,**grounding 在本轮 `index`**。省略 = 这轮读了、没东西标(只占覆盖率) |
| `rounds[].issues` | 否 | 主动声明的 issue 数组,每条 `{issue, indexes?}`:`indexes` 给了就 ground 在指定的几轮,否则默认本轮 `index`。**提交方只给 `issue` / `indexes`;`card_id` / `is_new` 是服务端输出,不在请求体里** |

> 一份提交 = 一份 mark。没东西标的轮照样写一条 `{index}`(只占覆盖)。

> wire 也接受 YAML(CLI 直接转发);字段同上。

### 副作用(写入顺序)

1. **乐观锁校验**:`last_index` == session `max(round_index)`?否 → 409,不写任何东西。
2. **rounds 校验**:首条 index==1 / 严格递增 / 不重复 / 范围内(违反 → 400,整份拒绝)。
2b. **覆盖率校验**:distinct round 数 < `ceil(0.9 × last_index)` → 400,**在任何写入之前**整份拒绝。
3. **解析每条 round 的 issue**(comment 的 `#…？` + 主动声明的 `issues`)→ embed 撞 `cards`(issue)向量库,按三岔:
   - **miss → 建新卡**:`issue` = 问题文本、自动生成 `card_id` = `card_<ULID>`、embed `issue` 写 `cards` collection、落 `cards/<bucket>/<card_id>/card.json`。
   - **hit → 关联**老卡(不动老卡)。
4. 服务端分配 `m<n>` → 插一行 `session_marks` + 落一个 `marks/m<n>.yaml`(含每条 round 的 `issues[]`,回填 `card_id` / `is_new`)。
5. 每个 issue 各记一条 [`card_sessions`](../../structure/v4/card-session.md):`mark` = `m<n>` + `indexes` = grounding 的 round(s)。**同一 mark 里多条 round 命中同一张卡 → MERGE 成一条 `card_sessions` 行**(PK `(card_id, session_id, mark)`),`indexes` 合并(如 round 37 & 50 → `"37,50"`)。embedding provider 失败 → 整份拒绝(503),无半截状态。

### 响应 `200`

```json
{
  "session_id": "sess_def456",
  "mark": "m1",
  "rounds": [
    {"index": 1, "issues": []},
    {"index": 37, "comment": "配 pty 时用户突然提了 tmux。#为什么 pty 会让用户想到 tmux？",
     "issues": [{"issue": "为什么 pty 会让用户想到 tmux", "card_id": "card_01jz8k2m", "is_new": true, "indexes": "37"}]}
  ]
}
```

### 状态码

| 码 | 情况 |
|---|---|
| `200` | 提交成功(返回服务端分配的 `mark`) |
| `400` | `rounds` 为空 / body 非法 / 首条 index≠1 / 非严格递增 / 重复 / 越界 / **覆盖率 < 90%** |
| `404` | `session_id` 不存在 |
| `409` | `last_index` ≠ session 当前最新 round index(标注期间来了新 round;重读再标) |
| `503` | 服务未就绪(searchbase 缺失 → `#…？` 无法撞库 → 整份拒绝) |

## GET /v4/sessions/{session_id}/marks

列这个 session 的所有 mark(**元信息**,来自 `session_marks`;正文不回)。要看一条 session 的 mark,直接 `read sess_…`(session 读取已把 `marks[]` 折进来),要看单条正文走 `read sess_…#m1`。

### 响应 `200`

```json
{
  "session_id": "sess_def456",
  "marks": [
    {"mark": "m1", "last_index": 41, "created_at": "2026-06-16T08:30:00Z"},
    {"mark": "m2", "last_index": 41, "created_at": "2026-06-16T08:30:00Z"}
  ]
}
```

## DELETE /v4/sessions/{session_id}/marks

**清空这个 session 的所有 mark**:删掉 session 目录下每个 `marks/*.yaml`、删掉 `session_marks` 里这个 session 的所有行、删掉 `card_sessions` 里这个 session 的所有出处边。**卡 / Position / review / link 一律不动**——只走 mark 本身 + 它的出处边。无 mark 的 session 删一次是 no-op 成功(`deleted_marks: 0`)。

### 响应 `200`

```json
{"session_id": "sess_def456", "deleted_marks": 2}
```

### 状态码

| 码 | 情况 |
|---|---|
| `200` | 清空成功(`deleted_marks` = 删了几条 mark;无 mark 也是 200,`deleted_marks: 0`) |
| `404` | `session_id` 不存在 |

> **状态:已实现(v1.1.x)**(机制见 [session-mark.md](../../works/v4/session-mark.md))。
