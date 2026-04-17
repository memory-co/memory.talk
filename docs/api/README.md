# API Reference

本地 API，CLI 通过调用这些接口实现功能。所有接口返回 JSON。

```
Sessions    POST   /sessions                 创建/导入 session
            GET    /sessions                 列出 sessions
            GET    /sessions/:id             读取 session rounds
            POST   /sessions/:id/tags        添加 tags
            DELETE /sessions/:id/tags        移除 tags

Cards       POST   /cards                    创建 card（自动 embedding）
            GET    /cards                    列出 cards
            GET    /cards/:id               读取 card

Links       POST   /links                    创建 link
            GET    /links?id=<ID>            查询关联
            DELETE /links/:link_id            删除 link（仅供人工管理）

Recall      POST   /recall                   向量检索

Status      GET    /status                   统计信息
```

数据结构定义见 [structure/](../structure/)。

注意：`sync` 命令没有对应 API，它是 CLI 层的胶水逻辑——读取平台本地文件，调用 sessions API 写入。
