# Links API

## POST /links

创建一条关联。

请求体：
```json
{
  "source_id": "card-a",
  "source_type": "card",
  "target_id": "card-b",
  "target_type": "card",
  "comment": "都在讨论向量库选型"
}
```

方向由 source → target 表达。

响应：
```json
{"status": "ok", "link_id": "01jzq7rm"}
```

`link_id` 自动生成，后续用于刷新 TTL 或删除。

## GET /links

查询某个对象的所有关联。

| 参数 | 说明 |
|------|------|
| `id` | 要查询的对象 ID（必填） |
| `type` | 筛选关联目标类型：`card` 或 `session`（可选） |

响应：Link 数组，包含两个方向的关联，每条带 `link_id`。

## DELETE /links/:link_id

按 `link_id` 删除一条关联。供人工管理使用，AI 不应调用——正常情况下 link 不会消失，只会因 TTL 耗尽而被遗忘。
