# setup

一次性初始化存储后端和目录结构。

```bash
memory-talk setup [--vector lancedb] [--relation sqlite] [--embedding local|dummy] [--data-root PATH]
```

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `--vector` | `lancedb` | 向量库后端 |
| `--relation` | `sqlite` | 关系库后端 |
| `--embedding` | `local` | Embedding 模型（`local` 需要 sentence-transformers，`dummy` 用于测试） |
| `--data-root` | `~/.memory-talk` | 数据根目录 |

输出示例：
```json
{
  "status": "ok",
  "data_root": "/home/user/.memory-talk",
  "vector_backend": "lancedb",
  "relation_backend": "sqlite",
  "embedding_backend": "local"
}
```

## settings.json

`setup` 运行后生成配置文件 `~/.memory-talk/settings.json`。

Schema：

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

**顶层**

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `vector` | object | | 向量库配置 |
| `relation` | object | | 关系库配置 |
| `embedding` | object | | Embedding 配置 |

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
