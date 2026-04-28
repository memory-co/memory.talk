# test_openai_embedding_start

OpenAI 兼容 embedding provider 启动场景 —— settings.json 配置一个真实的远端
embedding 服务(默认用 DashScope 的 `text-embedding-v4`),验证 `validate_embedder`
在 lifespan 启动里对远端做一次 probe 并成功。

## 前置依赖

**需要环境变量 `QWEN_KEY`**,值为 DashScope 的 API key:

```bash
export QWEN_KEY="sk-xxxxxxxxxxxx"
pytest memorytalk/tests/cli/server/test_openai_embedding_start/
```

**没设置 `QWEN_KEY` → 测试直接 FAIL,不跳过**。这是有意的 —— 配置里声明要走
OpenAI embedding,就必须能 probe 通;如果连 key 都没有,生产 server 也会拒绝启动,
测试如实把这件事报出来,而不是把"环境缺配置"的问题藏到 `skipped` 里。

## 场景

```
写 settings.json:
{
  "server": {"port": <random>},
  "embedding": {
    "provider": "openai",
    "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
    "auth_env_key": "QWEN_KEY",
    "model": "text-embedding-v4",
    "dim": 1024
  }
}
   ↓
memory-talk server start
   ↓
uvicorn 子进程 → lifespan startup → validate_embedder():
   - 读 os.environ["QWEN_KEY"]
   - POST https://dashscope.aliyuncs.com/.../embeddings {"input": ["ping"], ...}
   - 断言返回 data[0].embedding 长度 == 1024(dim 对齐)
   ↓
如 probe 成功:server 正常对外提供服务
如 probe 失败:lifespan 抛 EmbedderValidationError → SystemExit(2) → 子进程退出
              CLI server start wrapper 捕到并返回 {status: failed, error: ...}
```

## 覆盖的路径

- `get_embedder(config)` 工厂走 `openai` 分支,构造 `OpenAIEmbedder`
- `validate_embedder()` 真正发 httpx.AsyncClient POST 到 DashScope
- 网络路径 + 鉴权(Bearer token)+ 返回解析 + dim 校验
- `GET /v2/status` 返回 `embedding_provider: openai`

这是整个测试套里**唯一会发真实外网请求**的用例。其它测试都用 dummy provider。

## 关键断言

- `server start` 返回 `{status: started}`(不是 `failed`,说明 probe 成功)
- `GET /v2/status.embedding_provider == "openai"`
- `server stop` 返回 `{status: stopped}`

## Fixture

`settings.json` 是**直接可用的配置**(不 include 随机端口),测试加载它之后由
`server_env.write_settings()` 自动把 `server.port` 合并进去。

想换 embedding provider(vLLM、本地 ollama 兼容 API 等),只改这一份 settings.json
即可,test.py 不用动。

## 用例失败说明

如果测试失败,常见原因:

1. **`QWEN_KEY` 未设置** → `summary.error` 含 `"environment variable 'QWEN_KEY' is not set"`
2. key 失效或过期 → `summary.error` 含 "401 Unauthorized"
3. 网络不通 → `summary.error` 含 "ConnectError"
4. DashScope 端点改了 → 改 `settings.json` 里的 `endpoint`
5. `text-embedding-v4` 维度不再是 1024 → 改 `settings.json.embedding.dim`

## 和 no_config_start 场景的区别

| | no_config_start | openai_embedding_start |
|---|---|---|
| embedding provider | dummy | openai |
| 启动时有网络调用 | 否 | **有**(probe) |
| 跑 CI 不带 key | ✅ 正常通过 | ❌ **fail**(而不是 skip) |
| 覆盖 `validate_embedder` 分支 | dummy(trivial) | openai(真实端点) |
