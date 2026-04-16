# links

为已有 card 补建关联。

## links create

在两张已有 card 之间创建关联。

```bash
memory-talk links create '<JSON>'
```

JSON 字段：

| 字段 | 必填 | 说明 |
|------|------|------|
| `source_card_id` | 是 | 源 card ID |
| `target_card_id` | 是 | 目标 card ID |
| `link_type` | 是 | `temporal` / `topical` / `causal` |
| `weight` | 否 | 权重，默认 1.0 |

示例：
```bash
memory-talk links create '{
  "source_card_id": "card-a",
  "target_card_id": "card-b",
  "link_type": "causal",
  "weight": 0.9
}'
```
