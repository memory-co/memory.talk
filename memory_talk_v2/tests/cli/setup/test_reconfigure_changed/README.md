# test_reconfigure_changed

已存在 `settings.json`,wizard 改 `embedding.model`,验证:
- 文件被原子改写
- 摘要里 `changed` 列出修改的字段
- 因为 server 没在跑,只是简单提示而非询问重启

## 应答

`embedding provider` Enter(保持 openai),`endpoint` Enter,`auth_env_key` Enter,
`model` 输入新值 `text-embedding-v3`,`dim` Enter,后面全 Enter,server 启动选 `n`。

## 验证

- `settings.json` 里 `embedding.model == "text-embedding-v3"`
- 摘要含 `embedding.model` 字段名
- exit 0
