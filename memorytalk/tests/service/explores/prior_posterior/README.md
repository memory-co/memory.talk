# prior_posterior — 先验/后验切分

`service/explores.partition` + `ExploreService.get_partition`。

## 这个场景在测什么

- **全局池 − 驱动集**:cwd 落在 explore 目录下的 session 被排除;其余参与。
- **divider 含先验侧**(`<=`),canonical UTC-Z 字典序即时间序。
- **cwd 缺失 → 非驱动**,仍参与。
- `get_partition` 每次从当前 DB session 池实时算(线冻、归属活)。

## 不在这测什么

- `divider_at` 怎么冻 → `../create/`
- HTTP 视图 → `tests/api/explores/crud/`
