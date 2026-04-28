# test_first_install_local

第一次跑 `memory-talk setup`,用户选 local embedding(sentence-transformers)。
local 探针在 `validate_embedder` 里是"导入 SentenceTransformer + 加载 model"
—— 这一步会触发**真模型下载**,测试里要避开。

## 应答

| 步骤 | 应答 |
|---|---|
| install_mode | `2` |
| embedding provider | `local` |
| model | (Enter,默认 all-MiniLM-L6-v2) |
| dim | (Enter,默认 384) |
| vector | (Enter) |
| relation | (Enter) |
| port | (Enter) |
| start server? | `n` |

## 模拟

monkey-patch `validate_embedder` 让 local 分支直接通过(不真去拉模型)。

## 验证

- `settings.json` 里 `embedding.provider == "local"`,`model == "all-MiniLM-L6-v2"`,`dim == 384`
- 摘要里 `server | not_started · ...`(用户选了 n)
- exit 0
