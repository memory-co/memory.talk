# test_first_install_openai

第一次跑 `memory-talk setup`(没有现成 `settings.json`),用户选 openai
embedding,wizard 跑通。

## 输入应答(stdin 顺序)

| 步骤 | 应答 |
|---|---|
| install_mode | `2`(use current) |
| embedding provider | `openai` |
| endpoint | (Enter,接受默认 DashScope) |
| auth_env_key | (Enter,接受 `QWEN_KEY`) |
| model | (Enter,接受 `text-embedding-v4`) |
| dim | (Enter,接受 1024) |
| vector | (Enter,只有 lancedb) |
| relation | (Enter,只有 sqlite) |
| port | (Enter,接受 7788) |
| start server? | `y` |

## 验证

- `<data_root>/settings.json` 存在,内容含 openai provider + 正确 endpoint / model / dim
- 数据子目录(sessions / cards / links / vectors / logs/search)都建出来了
- stdout 摘要包含 `# setup · **ok**` 和 `embedding | openai · text-embedding-v4 · dim 1024`
- exit code 0

## 模拟

`mock_openai_probe(dim=1024)` 把 httpx 探针替成假向量 → 不打真 DashScope。
server start 在 fixture 里被替成 `{"status":"started", ...}`,不真起 uvicorn。
