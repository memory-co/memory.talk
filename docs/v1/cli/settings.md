# settings.json

配置文件路径：`~/.memory-talk/settings.json`

不存在时使用默认值。由 AI 直接读写，无需专门的 setup 命令。

## Schema

```json
{
  "vector": {
    "provider": "lancedb"
  },
  "relation": {
    "provider": "sqlite"
  },
  "embedding": {
    "provider": "local",
    "model": "all-MiniLM-L6-v2"
  }
}
```

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
