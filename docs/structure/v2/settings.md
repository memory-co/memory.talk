# settings.json

配置文件路径：`~/.memory.talk/settings.json`

不存在时使用默认值。由 AI 直接读写，无需专门的 setup 命令。

## Schema

```json
{
  "server": {
    "port": 7788
  },
  "vector": {
    "provider": "lancedb"
  },
  "relation": {
    "provider": "sqlite"
  },
  "embedding": {
    "provider": "dummy",
    "model": "all-MiniLM-L6-v2"
  },
  "ttl": {
    "card": {
      "initial": 2592000,
      "factor": 2.0,
      "max": 31536000
    },
    "link": {
      "initial": 1209600,
      "factor": 2.0,
      "max": 15768000
    }
  },
  "search": {
    "default_top_k": 10,
    "comment_max_length": 500,
    "search_log_retention_days": 0
  }
}
```

**server**

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `port` | integer | `7788` | API 服务监听端口 |

**vector**

| 字段 | 类型 | 默认值 | 可选值 | 说明 |
|------|------|--------|--------|------|
| `provider` | string | `lancedb` | `lancedb` / `qdrant` / `milvus` | 向量库后端 |

**relation**

| 字段 | 类型 | 默认值 | 可选值 | 说明 |
|------|------|--------|--------|------|
| `provider` | string | `sqlite` | `sqlite` / `postgresql` / `mysql` | 关系库后端 |

**embedding**

| 字段 | 类型 | 默认值 | 可选值 | 说明 |
|------|------|--------|--------|------|
| `provider` | string | `dummy` | `local` / `dummy` / `openai` | Embedding 后端 |
| `model` | string | `all-MiniLM-L6-v2` | 任意模型名 | 模型名称（`local` 时为 sentence-transformers 模型，`openai` 时为远端模型 id，如 `text-embedding-v4`） |
| `endpoint` | string? | `null` | OpenAI 兼容 `/v1/embeddings` URL | 仅 `openai` 后端使用，例如 `https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings` |
| `auth_key` | string? | `null` | 字面 API key,或 `${VAR}` 形式 | 仅 `openai` 后端使用。直接填字面值最简单;`${VAR}` 由 `string.Template.substitute` 在请求时从 `os.environ` 渲染。环境变量缺失会抛错(便于排查) |
| `dim` | integer | `384` | 正整数 | 向量维度，必须与 provider 实际输出一致（如 DashScope `text-embedding-v4` 为 `1024`） |
| `timeout` | float | `30.0` | 秒 | 仅 `openai` 后端使用，HTTP 请求超时 |

示例 1:字面 key:

```json
{
  "embedding": {
    "provider": "openai",
    "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
    "auth_key": "sk-abcdef-1234567890",
    "model": "text-embedding-v4",
    "dim": 1024
  }
}
```

示例 2:从环境变量读(需先 `export QWEN_KEY=...`):

```json
{
  "embedding": {
    "provider": "openai",
    "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
    "auth_key": "${QWEN_KEY}",
    "model": "text-embedding-v4",
    "dim": 1024
  }
}
```

> **迁移说明**:旧版本的 `auth_env_key` 字段(只存环境变量名)已被 `auth_key` 取代。带 `auth_env_key` 的 settings.json 会启动失败,请重跑 `memory.talk setup` 重建配置。

**ttl.card**

> **单位约定**：本文件所有 `ttl.*` 字段单位均为**秒**。API 响应里返回的 `ttl` 字段也是秒（计算公式 `expires_at - now`）。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `initial` | integer | `2592000` | 创建时的初始过期时长（秒），默认 30 天 |
| `factor` | float | `2.0` | 每次被 view 命中时，剩余 ttl 乘以此系数 |
| `max` | integer | `31536000` | ttl 上限（秒），默认 365 天 |

**ttl.link**

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `initial` | integer | `1209600` | 创建时的初始过期时长（秒），默认 14 天。仅适用于用户 link；默认 link 的 `ttl` 恒为 `0`（sentinel，不参与秒级计时） |
| `factor` | float | `2.0` | 每次被访问时，剩余 ttl 乘以此系数 |
| `max` | integer | `15768000` | ttl 上限（秒），默认 182 天 |

**search**

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `default_top_k` | integer | `10` | search 默认 top_k |
| `comment_max_length` | integer | `500` | `link.comment` 字数上限 |
| `search_log_retention_days` | integer | `0` | `search_log` 老化阈值（天）。`0` = 永不老化（默认）。>0 时，`created_at` 早于此阈值的行在下次 rebuild / 扫描时被清除 |

**v2 不再有 result_id**：v2 不发行"带 TTL 的追踪 token"——调用方直接用带前缀的裸 id（`card_<ULID>` / `sess_<ULID>` / `link_<ULID>`）操作所有端点。追踪由 AI session 的 tool-use 对话天然承担，见 [search-result.md](search-result.md)。
