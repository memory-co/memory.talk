# test_reconfigure_no_change

已存在 `settings.json`,跑 setup 全部 Enter 跳过。预期:**不重写文件**,
摘要里 `changed | nothing — config unchanged`。

## 验证幂等性

- 跑 setup 前记 `settings.json` 的 mtime
- 跑完后 mtime 跟之前一致(没有重写)
- 摘要 stdout 含 `nothing — config unchanged`

## 应答

| 步骤 | 应答 |
|---|---|
| install_mode | `2` |
| embedding provider | (Enter,保持 openai) |
| endpoint | (Enter) |
| auth_env_key | (Enter) |
| model | (Enter) |
| dim | (Enter) |
| vector | (Enter) |
| relation | (Enter) |
| port | (Enter) |

## 模拟

mock_openai_probe(1024) —— 即便没改字段,wizard 在第一次 first_install
的判断逻辑里,只有当 embedding section diff 才探针,所以这里**不应该探针**;
mock 只是兜底防止意外触发真网络。
