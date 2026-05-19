# Status API

## GET /v3/status

服务健康检查 + 数据统计 + provider 信息。无 body。

### 响应

```json
{
  "data_root": "/home/user/.memory-talk",
  "settings_path": "/home/user/.memory-talk/settings.json",
  "status": "running",
  "sessions_total": 47,
  "cards_total": 184,
  "reviews_total": 92,
  "searches_total": 1083,
  "recalls_total": 4221,
  "embedding_provider": "openai",
  "embedding_model": "text-embedding-v4",
  "embedding_dim": 1024,
  "vector_provider": "lancedb",
  "relation_provider": "sqlite",
  "sync_enabled": true
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `data_root` | string | 数据根目录绝对路径 |
| `settings_path` | string | settings.json 路径 |
| `status` | string | 永远是 `"running"` —— 能拿到响应就是 running;连不上就是 not_running(CLI 层判断) |
| `sessions_total` | integer | 已 ingest 的 session 数 |
| `cards_total` | integer | 累计创建的 card 数(append-only,永不减少) |
| `reviews_total` | integer | 累计创建的 review 数 |
| `searches_total` | integer | `search_log` 表行数(被 retention 老化掉的不计) |
| `recalls_total` | integer | `recall_log` 表行数(被重启 / rebuild 清掉的不计) |
| `embedding_provider` | string | `local` / `openai` / `dummy` |
| `embedding_model` | string | 当前模型名 |
| `embedding_dim` | integer | 向量维度 |
| `vector_provider` | string | `lancedb`(目前唯一) |
| `relation_provider` | string | `sqlite`(目前唯一) |
| `sync_enabled` | boolean | sync watcher 当前是否在跑(等价于 `GET /v3/sync/status.running`) |

### 错误

只有 500(内部异常)。**没有 404 / 401** —— 这是 hello check 端点,不参数化。

### 跟 v2 的差异

- **新增** `reviews_total` / `recalls_total` / `embedding_*`(细分到 model/dim)/ `sync_enabled`
- **删** `tags_total` / `links_total` —— v3 无 tag / link
- `searches_total` 字段名沿用 v2

### 用途

主要给 CLI 的 `server status` 命令和外部监控用。CLI 进程探测"server 起来没"也走这个端点 —— 连得上 200 就 ok,任何其它响应(包括 connection refused)就当 not_running。
