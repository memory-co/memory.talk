# settings.json

配置文件路径：`~/.memory-talk/settings.json`

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
    "provider": "local",
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
| `auth_env_key` | string? | `null` | 环境变量名 | 仅 `openai` 后端使用，从该环境变量读取 Bearer Token，例如 `QWEN_KEY` |
| `dim` | integer | `384` | 正整数 | 向量维度，必须与 provider 实际输出一致（如 DashScope `text-embedding-v4` 为 `1024`） |
| `timeout` | float | `30.0` | 秒 | 仅 `openai` 后端使用，HTTP 请求超时 |

示例：使用 OpenAI 兼容的 DashScope `text-embedding-v4`（需先 `export QWEN_KEY=...`）：

```json
{
  "embedding": {
    "provider": "openai",
    "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
    "auth_env_key": "QWEN_KEY",
    "model": "text-embedding-v4",
    "dim": 1024
  }
}
```

**ttl.card**

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `initial` | integer | `2592000` | 创建时的初始过期时长（秒），默认 30 天 |
| `factor` | float | `2.0` | 每次被 recall 命中时，剩余 ttl 乘以此系数 |
| `max` | integer | `31536000` | ttl 上限（秒），默认 365 天 |

**ttl.link**

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `initial` | integer | `1209600` | 创建时的初始过期时长（秒），默认 14 天 |
| `factor` | float | `2.0` | 每次被访问时，剩余 ttl 乘以此系数 |
| `max` | integer | `15768000` | ttl 上限（秒），默认 182 天 |
