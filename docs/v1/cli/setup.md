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
