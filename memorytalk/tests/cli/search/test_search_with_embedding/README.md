# test_search_with_embedding

`memory-talk search <query>` 使用**真实 OpenAI 兼容 embedding provider**
(默认 DashScope `text-embedding-v4`)的场景测试。

## 前置依赖

**需要环境变量 `QWEN_KEY`**:

```bash
export QWEN_KEY="sk-xxxxxxxxxxxx"
pytest memorytalk/tests/cli/search/test_search_with_embedding/
```

**没设 `QWEN_KEY` → 测试直接 FAIL,不跳过**。和 `tests/cli/server/test_openai_embedding_start/`
同一策略:配置声明要走 openai embedding,就必须 probe 通;连 key 都没有时藏到
`skipped` 里是在掩盖环境问题。

## 场景

```
fixture: openai_cli_env(来自 tests/cli/search/conftest.py)
   写 settings.json → embedding.provider=openai → TestClient 触发 lifespan →
   validate_embedder → probe DashScope → 成功就 yield,失败就 raise
        ↓
seed:  await app.state.sessions.ingest(...)            # service 直调
       await app.state.cards.create(CreateCardRequest(...))
              └─── 这步会调用 OpenAIEmbedder.embed_one(summary) —— 真网络请求 #1
        ↓
CLI:   memory-talk search "LanceDB"
        ↓ _http.api() 构 TestClient(ASGI) → POST /v2/search
       SearchService.search:
         embedder.embed_one("LanceDB") —— 真网络请求 #2
         LanceDB hybrid: 用 query 向量 + FTS 做 RRF 融合
        ↓
CLI 输出 JSON,测试 parse 后对比 shape + 命中
```

## 关键断言

- `exit_code == 0`(没到 0 说明 embedding 调用失败 / API 错误)
- `search_id` 前缀 `sch_`
- `query` 字段回显
- `cards.count >= 1`(真实 embedding + FTS hybrid 至少能命中种子 card)
- 命中的 card `summary` 包含 "LanceDB"
- `search_log.count() == 1`(副作用落库)

**不测**排序精度和 score 数值 —— 这些由独立的搜索质量测试层处理。

## 总共会真实调用 DashScope 几次

- fixture 启动时 `validate_embedder` 的 probe:1 次
- seed 阶段 `cards.create` 的 summary embed:1 次
- CLI search 的 query embed:1 次

合计 3 次。单次调用很快(< 1s),对 DashScope 配额极友好。

## 和现有 dummy 测试的关系

| | `test_search_plain_query/` | `test_search_with_where/` | `test_search_with_embedding/`(本场景) |
|---|---|---|---|
| embedder | dummy(hash) | dummy | **openai(DashScope)** |
| 真实网络 | 无 | 无 | **有**(3 次) |
| 主测什么 | 响应结构契约 | DSL whitelist 过滤 | 真实 embedding 路径完整可用 |
| QWEN_KEY 未设 | 不受影响 | 不受影响 | **FAIL**(不 skip) |

前两个用 dummy 覆盖**结构层**和**DSL 层**,这个补**真实 provider 层**。

## 失败诊断

- `exit_code != 0` 且错误含 `"environment variable 'QWEN_KEY' is not set"` → 没设 key
- 错误含 `401 Unauthorized` → key 失效/过期
- 错误含 `ConnectError` → 网络不通 / DNS / 防火墙
- `dim mismatch` → DashScope 改了 `text-embedding-v4` 的维度,改 `conftest.py` 里 `dim=1024`
