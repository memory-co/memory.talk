# link

管理关联关系。link 可以连接任意类型：card、session。每条 link 有唯一 `link_id`。

## link create

创建一条关联。

```bash
memory-talk link create '<JSON>'
```

JSON 字段：

| 字段 | 必填 | 说明 |
|------|------|------|
| `source_id` | 是 | 源 ID |
| `source_type` | 是 | `card` 或 `session` |
| `target_id` | 是 | 目标 ID |
| `target_type` | 是 | `card` 或 `session` |
| `comment` | 否 | 说明为什么关联 |

方向由 source → target 天然表达。`link_id` 自动生成。

示例：
```bash
memory-talk link create '{
  "source_id": "card-a",
  "source_type": "card",
  "target_id": "card-b",
  "target_type": "card",
  "comment": "都在讨论向量库选型"
}'
```

## link list

查询某个对象的所有关联。

```bash
memory-talk link list <ID> [--type card|session]
```

`--type` 可筛选关联目标的类型。每条结果带 `link_id`。
