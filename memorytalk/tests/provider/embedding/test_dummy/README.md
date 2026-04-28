# test_dummy

`validate_embedder()` 在 dummy provider 下的快速通过路径。

## 场景矩阵

| 测试函数 | 验证什么 |
|---|---|
| `test_dummy_passes` | settings.json 配 `provider=dummy`,validate 直接通过(不打网络)|

## 覆盖的代码路径

- `provider/embedding.py::validate_embedder` 的 dummy 短路分支
- 该分支不需要 env key、不需要打 HTTP,startup 应该零成本

## 为什么需要这条快速路径

测试全套(api/cli/service)都用 dummy embedder,如果 validate 在 dummy 下也
要打网络,所有不带 QWEN_KEY 的测试就得改用 mock —— noise 远大于收益。
dummy 是"假装能 embed"的 fallback,validate 看见 dummy 就直接放行。
