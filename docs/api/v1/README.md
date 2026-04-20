# API Reference (v1)

本地 API，CLI 通过调用这些接口实现功能。所有接口返回 JSON。所有 v1 路由统一以 `/v1` 前缀挂载。

```
Sessions    POST   /v1/sessions                 创建/导入 session
            GET    /v1/sessions                 列出 sessions
            GET    /v1/sessions/:id             读取 session rounds
            POST   /v1/sessions/:id/tags        添加 tags
            DELETE /v1/sessions/:id/tags        移除 tags

Cards       POST   /v1/cards                    创建 card（自动 embedding）
            GET    /v1/cards                    列出 cards
            GET    /v1/cards/:id                读取 card

Links       POST   /v1/links                    创建 link
            GET    /v1/links?id=<ID>            查询关联
            DELETE /v1/links/:link_id           删除 link（仅供人工管理）

Recall      POST   /v1/recall                   向量检索

Status      GET    /v1/status                   统计信息
```

数据结构定义见 [structure/v1/](../../structure/v1/)。

注意：`sync` 命令没有对应 API，它是 CLI 层的胶水逻辑——读取平台本地文件，调用 sessions API 写入。
