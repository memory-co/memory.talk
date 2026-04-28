# test_openai_probe

`validate_embedder()` 真的会打一次 HTTP 探针,验证 endpoint 能返回向量、
且向量维度跟 settings 里声明的 `dim` 一致。

## 场景矩阵

| 测试函数 | 模拟返回 | 预期 |
|---|---|---|
| `test_openai_probe_dim_mismatch` | 384-d 向量(配置里 dim=1024)| `EmbedderValidationError("dim mismatch")` |
| `test_openai_probe_success` | 1024-d 向量 | 通过,无异常 |

## 覆盖的代码路径

- `validate_embedder` 的探针构造:`POST <endpoint>` 带 `model` 和测试字符串
- 解析 `data[0].embedding`,长度跟 `settings.embedding.dim` 比对
- httpx.AsyncClient 通过 monkeypatch + AsyncMock 替身,不打真网络

## 为什么必须验 dim

embedding 长度跟 LanceDB 表 schema 强绑定 —— 配错一次 dim,所有后续
`add_card` 都会失败。在 startup 阶段做一次主动探针,把"配置错"提前到
"server 起不来",而不是"第一张卡创建时炸"。
