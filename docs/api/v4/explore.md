# Explore API

CLI `explore` 命令的 backend 数据出口。三个 GET 端点 —— **CLI / agent 都通过 HTTP 查**,不直接读 `~/.claude/projects/*.jsonl`。

CLI 对应 [`explore`](../../cli/v4/explore.md) 的 `pending` / `list` / `detail` 子命令。`auto` / `manual` / `resume` 是本地进程控制,不走 HTTP API。

> **v4 唯一变化**:
> - 路由从 `/v3/explore/*` 挪到 **`/v4/explore/*`** 前缀,GET 端点的请求 / 响应形态不变。
> - 抽卡产物从 insight 卡(一句陈述)换成 **v4 卡**(一个问题 Issue + 若干答案 Position);`list` / `detail` 里 `cards[]` 指的是 v4 卡。
> - 抽卡的**写路径**不是独立 explore 写端点,而是逐 round 注解 —— 见 [`session-marks.md`](session-marks.md)(`POST /v4/sessions/{id}/marks`,mark 里 `#…？` 自动建卡)。

## GET /v4/explore/pending

返回 backend 视角下"还没被任何卡引用过、可作为抽取候选"的 session 列表。

### 形式化定义

```
pending = {
  session
  | NOT EXISTS card 引用 session.session_id
  AND session.metadata.cwd NOT startswith <settings.explore.cwd>
  AND session.last_at <= now() - 30 minutes
}
```

三条规则:
- **未被引用**:还没有任何卡引用过这条 session
- **不是 explore 自己产出的**:排除 `<explore.cwd>` 下的 session(避免套娃)
- **不再"active"**:最近一轮 < 30 分钟前的 session 可能还在跑,暂不进队列

### 查询参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `limit` | `50` | 上限 |

### 响应

```json
{
  "count": 5,
  "sessions": [
    {
      "session_id": "sess_01k...",
      "started_at": "2026-05-12T14:24:00Z",
      "last_at": "2026-05-12T17:11:00Z",
      "rounds": 28,
      "cwd": "/home/me/proj-a"
    }
  ]
}
```

| 字段 | 说明 |
|---|---|
| `count` | 实际返回数(可能 < `limit`) |
| `sessions[].session_id` | 带 `sess_` 前缀 |
| `sessions[].cwd` | `metadata.cwd`,展平到顶层方便扫读 |

按 `last_at` 倒序(最近活跃的优先)。

## GET /v4/explore/list

列出 **explore namespace** 下的 session(`metadata.cwd` startswith `<settings.explore.cwd>`)—— explore 自己跑出来的 session 历史。

### 查询参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `limit` | `50` | 上限 |

### 响应

```json
{
  "explore_cwd": "/home/user/.memory.talk/explore",
  "count": 3,
  "sessions": [
    {
      "session_id": "sess_01k...",
      "started_at": "2026-05-03T10:24:00Z",
      "last_at": "2026-05-03T10:38:00Z",
      "rounds": 14,
      "cards": 3,
      "reviews": 1,
      "status": "done"
    }
  ]
}
```

| 字段 | 说明 |
|---|---|
| `sessions[].cards` | 本 session 产出的 v4 卡数 |
| `sessions[].reviews` | 本 session 产出的 review 数 |
| `sessions[].status` | 弱启发(仅显示用):`active`(`last_at` < 30m)/ `done`(`last_at` ≥ 30m 且 `cards + reviews > 0`)/ `abandoned`(`last_at` ≥ 1h 且 `cards + reviews = 0`) |

按 `started_at` 倒序。

## GET /v4/explore/detail/{sid}

某条 explore session 的产出详情。`{sid}` 接 `sess_` 前缀的 id 或裸 UUID,服务端按需补前缀。

### 响应

```json
{
  "session": {
    "session_id": "sess_01k...",
    "source": "claude-code",
    "started_at": "2026-05-03T10:24:00Z",
    "last_at": "2026-05-03T10:38:00Z",
    "rounds": 14,
    "cwd": "/home/user/.memory.talk/explore",
    "status": "done"
  },
  "cards": [
    {
      "card_id": "card_01jz8k2m",
      "issue": "用户偏好什么回答风格?",
      "created_at": "2026-05-03T10:28:00Z",
      "first_round_index": 5
    }
  ],
  "reviews": [
    {
      "review_id": "review_01jzr5kq",
      "card_id": "card_01jz8k2m",
      "position": "p1",
      "argument": -1,
      "indexes": "9-11",
      "comment": "原以为 mmap 在 NFS 上没事...",
      "created_at": "2026-05-03T10:35:00Z"
    }
  ]
}
```

**聚焦本次抽取产出** —— 不展开 round 内容。要看对话原文走 `POST /v4/read {id: "sess_01k..."}`。

| 字段 | 说明 |
|---|---|
| `cards[].issue` | 产出的 v4 卡的问题文本 |
| `cards[].first_round_index` | 本 session 里**第一次**触发本卡的 round 编号(最小 index),方便 detail UI 排序 |
| `reviews[].card_id` + `reviews[].position` | 这条 review 表态的 Position(寻址 `card_id#p<n>`;v4 review target 是 Position,不是整张卡。Position 无独立 id,是卡的附属) |
| `reviews[].argument` | `+1` / `0` / `-1` |

### namespace 校验

`detail` 会验证 `session.metadata.cwd` startswith `<settings.explore.cwd>`:不通过返 **403 `not in explore namespace`**(不是 404,因为 session 实际存在,只是不属于 explore 视角)。

### 错误

| 情况 | 状态 |
|---|---|
| `{sid}` 在 sessions 表里查不到 | 404 |
| `{sid}` 存在但 cwd 不在 explore namespace | 403, `not in explore namespace` |
| `{sid}` 前缀 / 格式不合法 | 400 |

## 副作用

三个端点**全部纯只读** —— 不修改任何对象、不刷计数、不写事件。

### 为什么 explore detail 用 403 而不是 404

`{sid}` 在 sessions 表里**确实存在**,只是不属于 explore namespace。404 会让调用方误以为 sync 还没追上。403 明确说"权限/范围问题":这条 session 你看,但**不能从 explore 视角看**。
