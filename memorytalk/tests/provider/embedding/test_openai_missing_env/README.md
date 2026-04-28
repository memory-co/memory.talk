# test_openai_missing_env

`validate_embedder()` 在 openai provider 下,**环境变量缺失**就 fail-fast,
不打网络。

## 场景矩阵

| 测试函数 | 验证什么 |
|---|---|
| `test_openai_missing_env` | settings 指向 `auth_env_key=UNIT_TEST_KEY`,该环境变量未设 → `EmbedderValidationError`,错误消息含变量名 |

## 覆盖的代码路径

- `provider/embedding.py::validate_embedder` 在 openai 分支里读 env
- env 不存在时早返回,不发 HTTP
- 错误消息把 env 变量名带出来,运维一眼能看出"缺哪个 key"

## 为什么不打网络再失败

打网络再失败会浪费一次 401 round-trip,而且错误信息是 "Invalid API key"
这种通用文案,跟"我的 .env 没加载"或"我跑错了 settings.json"难区分。
读到 env 缺失就立即报错,定位精准。
