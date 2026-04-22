# Session

Session 是从平台导入的一段原始对话，由 `sync` 命令写入。

## 存储路径

```
sessions/{source}/{id[0:2]}/{session_id}/
├── meta.json
└── rounds.jsonl
```

- `meta.json`：会话元数据（session_id, source, tags, round_count 等）
- `rounds.jsonl`：每行一个 Round JSON 对象

## Schema

```json
{
  "session_id": "sess_abc123",
  "source": "claude-code",
  "created_at": "2026-04-10T14:30:00Z",
  "metadata": {
    "project": "/home/user/myapp"
  },
  "tags": ["claude", "project:myapp"],
  "rounds": [
    {
      "index": 1,
      "round_id": "da33fa35",
      "parent_id": null,
      "timestamp": "2026-04-10T14:30:05Z",
      "speaker": "user",
      "role": "human",
      "content": [{"type": "text", "text": "向量库选型，ChromaDB 和 LanceDB 哪个好？"}],
      "is_sidechain": false,
      "cwd": "/home/user/myapp"
    },
    {
      "index": 2,
      "round_id": "ddda3122",
      "parent_id": "da33fa35",
      "timestamp": "2026-04-10T14:30:10Z",
      "speaker": "assistant",
      "role": "assistant",
      "content": [
        {"type": "thinking", "thinking": "用户在问向量库选型..."},
        {"type": "text", "text": "推荐 LanceDB，零依赖、嵌入式架构。"}
      ],
      "is_sidechain": false,
      "cwd": "/home/user/myapp",
      "usage": {"input_tokens": 28324, "output_tokens": 592}
    }
  ],
  "round_count": 20,
  "synced_at": "2026-04-16T08:00:00Z"
}
```

## 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | string | 唯一标识，形如 `sess_<platform_id>`。前缀 `sess_` 由服务端入库时加上（平台原始文件名不带前缀） |
| `source` | string | 来源平台（`claude-code` / `codex` / `openclaw`） |
| `created_at` | string | 对话创建时间（取第一条 round 的时间戳） |
| `metadata` | object | 平台特有的扩展信息（project、model、title、agent_name、version 等） |
| `tags` | string[] | 自由标签，`key:value` 格式 |
| `rounds` | Round[] | 对话轮次，每条通过 `parent_id` 指向上一条形成链表 |
| `round_count` | integer | 总轮次数 |
| `synced_at` | string | 导入时间 |

## Round（Session 中）

Session 的 Round 是原始对话的忠实记录，保留完整结构。

| 字段 | 类型 | 说明 |
|------|------|------|
| `index` | integer | 会话内自增编号，从 1 开始，按 `rounds` 数组顺序递增。sidechain round 也占号段，不重置。v2 新增，给人 / LLM 用的稳定短编号，也是 `card` 写入时引用 round 的键 |
| `round_id` | string | 唯一标识（对应平台的 uuid） |
| `parent_id` | string\|null | 前一个 round 的 ID，首条为 null。形成链表，支持分叉 |
| `timestamp` | string\|null | 时间戳 |
| `speaker` | string | 物理身份（谁在说） |
| `role` | string | 逻辑身份（`human` / `assistant` / `system` / `tool`） |
| `content` | ContentBlock[] | 内容块列表 |
| `is_sidechain` | boolean | 是否是分支对话，默认 false |
| `cwd` | string\|null | 当前工作目录 |
| `usage` | object\|null | token 消耗（仅 assistant round 有），含 `input_tokens`、`output_tokens` |

### ContentBlock

| type | 字段 | 说明 |
|------|------|------|
| `text` | `text` | 文本内容 |
| `code` | `language`, `text` | 代码块 |
| `thinking` | `thinking` | AI 思考过程 |

### 工具调用场景

工具调用在平台中是两条独立消息：assistant 发出 tool_use，user 返回 tool_result。以下是 Claude Code 原始格式和我们的映射格式对照。

**Claude Code 原始格式：**

assistant 消息（发起工具调用）：
```json
{
  "type": "assistant",
  "uuid": "187c6576-875f-4e3e-8fd8-f21fe60190b0",
  "parentUuid": "81b3ccfc-c81c-45db-acd0-547f8512d86c",
  "timestamp": "2026-04-13T12:42:54.235Z",
  "isSidechain": false,
  "cwd": "/home/user/myapp",
  "message": {
    "role": "assistant",
    "content": [
      {
        "type": "tool_use",
        "id": "toolu_01YCSMUFs1pAhc786qzPUiS2",
        "name": "Read",
        "input": {"file_path": "/home/user/myapp/pyproject.toml"}
      }
    ]
  }
}
```

user 消息（返回工具结果）：
```json
{
  "type": "user",
  "uuid": "c3270a84-a147-4a5a-9e64-6eab5d54d36a",
  "parentUuid": "187c6576-875f-4e3e-8fd8-f21fe60190b0",
  "timestamp": "2026-04-13T12:42:54.255Z",
  "isSidechain": false,
  "cwd": "/home/user/myapp",
  "message": {
    "role": "user",
    "content": [
      {
        "type": "tool_result",
        "tool_use_id": "toolu_01YCSMUFs1pAhc786qzPUiS2",
        "content": "[project]\nname = \"memory-talk\"\nversion = \"0.2.0\"\n..."
      }
    ]
  }
}
```

**映射为 memory.talk Session Round：**

```json
[
  {
    "index": 7,
    "round_id": "187c6576",
    "parent_id": "81b3ccfc",
    "timestamp": "2026-04-13T12:42:54.235Z",
    "speaker": "assistant",
    "role": "assistant",
    "content": [{"type": "text", "text": "[Read] /home/user/myapp/pyproject.toml"}],
    "is_sidechain": false,
    "cwd": "/home/user/myapp"
  },
  {
    "index": 8,
    "round_id": "c3270a84",
    "parent_id": "187c6576",
    "timestamp": "2026-04-13T12:42:54.255Z",
    "speaker": "system",
    "role": "tool",
    "content": [{"type": "text", "text": "[project]\nname = \"memory-talk\"\nversion = \"0.2.0\"\n..."}],
    "is_sidechain": false,
    "cwd": "/home/user/myapp"
  }
]
```

映射要点：
- `uuid` → `round_id`，`parentUuid` → `parent_id`
- tool_use 的 `name` + `input` 拼成 text（如 `[Read] path`）
- tool_result 的 `content` 直接作为 text
- tool_result 的 `role` 映射为 `tool`（区分人类输入），`speaker` 为 `system`
- 原始的 `tool_use.id` / `tool_result.tool_use_id` 关联关系通过 `parent_id` 链隐含，不需要额外字段

与 Talk-Card 中的 Round 不同——Talk-Card 的 round 极度精简，只有 `{role, text}`。Session 是录像，Talk-Card 是记忆。
