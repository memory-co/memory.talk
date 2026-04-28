# test_openai_invalid_endpoint

`auth_env_key` 在,但 `endpoint` 是个无人接听的地址 —— `validate_embedder`
应该探测到失败,server 起不来。覆盖"key 没问题但 endpoint 错"这一档,跟
sibling `test_openai_embedding_start/`(全好)和 `test_no_config_start/`
(全无配置)正交。

## 场景

- `provider=openai`,`auth_env_key=FAKE_EMB_KEY`(在 monkeypatch 里设上)
- `endpoint=http://127.0.0.1:<random_free_port>/v1/embeddings` —— 那个端口
  没人监听,probe 会立刻拿到 connection refused
- `timeout=3.0`(把 embedding 探针的等候上限砍到 3 秒,而不是默认 30 秒)

## 预期

`server start` 子进程拉起 → lifespan 跑 `validate_embedder` → httpx 对那个
本地端口发 POST → connect refused → `EmbedderValidationError("openai embedder: ...")`
→ lifespan 捕获 → `SystemExit(2)`。

CLI 父进程看见子进程死,要么:
1. 父亲的 1.2s 探查窗口内子进程已经死了 → `start()` 输出 `{"status":"failed", "exit_code":2, "error": "..."}`,断言 `error` 含 "embedding"
2. 极少数情况父亲先看了一眼觉得还活着 → 输出 `{"status":"started"}` —— 这种情况下用 `wait_ready(timeout=3.0)` 兜底,server 永远不会响应 `/v2/status`,最终 raise

两条路都验证"无效 endpoint 起不来"这个契约。

## 为什么把 embedding timeout 砍到 3 秒

默认 30 秒是给生产用的(慢网/嵌入服务偶发抽风时不要立刻挂)。测试场景下 30 秒
干等没有意义 —— connect-refused 本来就是毫秒级返回,3 秒已经远远够用,且即使
OS 出怪事(比如包被 firewall 黑洞)也不会让测试卡满半分钟。
