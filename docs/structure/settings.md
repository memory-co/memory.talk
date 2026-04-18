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
| `provider` | string | `local` | `local` / `dummy` | Embedding 后端 |
| `model` | string | `all-MiniLM-L6-v2` | 任意 sentence-transformers 模型名 | 模型名称（`local` 后端时生效） |

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
