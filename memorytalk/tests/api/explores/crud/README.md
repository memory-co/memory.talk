# crud — /v3/explores 端点

`api/explores.py`。

## 这个场景在测什么

- `POST /v3/explores`:冻结 divider,回 `prior_count` / `posterior_count`。
- `GET /v3/explores/{eid}`:manifest + 实时先验/后验堆。

## 不在这测什么

- divider 冻结 / 切分逻辑本身 → `tests/service/explores/`
- card/review 关联戳 → `../association/`
