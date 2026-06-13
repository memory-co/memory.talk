# create — 创建 explore，冻结 divider

`ExploreService.create` (`service/explores.py`)。

## 这个场景在测什么

传入口会话时,读它**创建那一刻**的 `last_round_update_time` 作为 `divider_at`
存进库,并分配一个工作区目录——之后入口会话再更新也不动这条线。

## 不在这测什么

- 先验/后验怎么切 → `../prior_posterior/`
- HTTP 端点 → `tests/api/explores/crud/`
