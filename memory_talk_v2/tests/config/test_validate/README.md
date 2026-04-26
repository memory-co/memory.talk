# test_validate

`Config.validate()` —— startup 前的健康检查,主要用来挡住 v1 残留数据。

## 场景矩阵

| 测试函数 | 验证什么 |
|---|---|
| `test_validate_passes_on_empty_root` | 空 data_root 没有 memory.db,validate 不抛错(首次启动场景) |
| `test_validate_rejects_v1_residue` | data_root 里有 v1 schema(`recall_log` 表)→ `ConfigValidationError`,错误消息含表名 |

## 覆盖的代码路径

- `config.py::Config.validate()` 的 SQLite schema 检查
- v1 残留检测:打开 memory.db,看是否有 `recall_log` / 其他 v1 表

## 为什么挡 v1 残留

v2 跟 v1 的 schema 完全不同。同一 data_root 同时用过两个版本会导致表混杂、
SQL 报错难定位。validate 提前在 startup 报清楚"这是个 v1 旧根,别用",
让 ops 自己决定备份/迁移/换 root。
