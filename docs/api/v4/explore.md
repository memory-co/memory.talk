# Explore API

CLI `explore` 命令的 backend 数据出口。三个 GET 端点 —— **CLI / agent 都通过 HTTP 查**,不直接读 `~/.claude/projects/*.jsonl`。

CLI 对应 [`explore`](../../cli/v4/explore.md) 的 `pending` / `list` / `detail` 子命令。`auto` / `manual` / `resume` 是本地进程控制,不走 HTTP API。

## GET /v4/explore/pending

返回 backend 视角下"还没被任何 card 引用过、可作为抽取候选"的 session 列表。

### 形式化定义

```
pending = {
  session
  | NOT EXISTS card.rounds[*].session_id = session.session_id
  AND session.metadata.cwd NOT startswith <settings.explore.cwd>
  AND session.last_at <= now() - 30 minutes
}
```

三条规则:
- **未被引用**:还没有任何 card 的 rounds 引用过这条 session
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
| `sessions[].cards` | 本 session 产出的 card 数 = `COUNT cards WHERE EXISTS round.session_id = sid` |
| `sessions[].reviews` | 本 session 产出的 review 数 = `COUNT reviews WHERE session_id = sid` |
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
      "insight": "选定 LanceDB 做向量存储",
      "created_at": "2026-05-03T10:28:00Z",
      "first_round_index": 5
    }
  ],
  "reviews": [
    {
      "review_id": "review_01jzr5kq",
      "card_id": "card_01jzpold99",
      "score": -1,
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
| `cards[].first_round_index` | 本 session 里**第一次**触发本 card 的 round 编号(最小 index),方便 detail UI 排序 |

### namespace 校验

`detail` 会验证 `session.metadata.cwd` startswith `<settings.explore.cwd>`:不通过返 **403 `not in explore namespace`**(不是 404,因为 session 实际存在,只是不属于 explore 视角)。

### 错误

| 情况 | 状态 |
|---|---|
| `{sid}` 在 sessions 表里查不到 | 404 |
| `{sid}` 存在但 cwd 不在 explore namespace | 403, `not in explore namespace` |
| `{sid}` 前缀 / 格式不合法 | 400 |

## 副作用

三个端点**全部纯只读** —— 不修改任何对象、不刷 stats、不写事件。

## 跟 v2 的差异

v2 explore CLI **不通过 backend** —— 直接读 `~/.claude/projects/<explore-project-id>/*.jsonl`。v3 把这套搬到 backend HTTP,统一数据源。

v2 没有对应的 API 端点;v3 新增这 3 个 GET。

### 为什么 explore detail 用 403 而不是 404

`{sid}` 在 sessions 表里**确实存在**,只是不属于 explore namespace。404 会让调用方误以为 sync 还没追上。403 明确说"权限/范围问题":这条 session 你看,但**不能从 explore 视角看**。
