# Status API

## GET /v2/status

返回服务和存储统计。CLI 的 `memory-talk server status` 直接调这个端点——能连上就是 running，连不上视为 not_running。

无请求参数。

## 响应

```json
{
  "data_root": "/home/user/.memory-talk",
  "settings_path": "/home/user/.memory-talk/settings.json",
  "status": "running",
  "sessions_total": 12,
  "cards_total": 47,
  "links_total": 23,
  "searches_total": 108,
  "vector_provider": "lancedb",
  "relation_provider": "sqlite",
  "embedding_provider": "dummy"
}
```

| 字段 | 说明 |
|------|------|
| `data_root` | 数据根目录 |
| `settings_path` | 当前生效的 settings.json 路径 |
| `status` | 恒为 `running`（连不上就不会有响应） |
| `sessions_total` | session 总数 |
| `cards_total` | card 总数 |
| `links_total` | link 总数（含默认 link 与用户 link，含已过期） |
| `searches_total` | 累计 search 次数（v2 新增——v2 把 search 作为主读路径，这个数字能快速看出"这台机器的记忆被多频繁地检索"） |
| `vector_provider` / `relation_provider` / `embedding_provider` | 当前生效的 provider 实现 |

## 错误

正常情况下 200。无 4xx——所有参数都是无关的。500 仅在底层存储查询失败时出现。
