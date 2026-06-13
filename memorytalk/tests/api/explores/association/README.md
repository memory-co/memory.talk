# association — card/review 盖 explore_id

`POST /v3/cards` / `POST /v3/reviews` 带 `explore_id`。

## 这个场景在测什么

带 `explore_id` 创建时,在 `cards.explore_id` / `reviews.explore_id` 盖一个
**瘦关联戳**。只是关联标记,不是门(君子协定不强制引用约束)。

## 不在这测什么

- card/review 自身创建逻辑 → `tests/api/test_cards.py` / `test_reviews.py`
- explore 的创建 / 切分 → `../crud/`
