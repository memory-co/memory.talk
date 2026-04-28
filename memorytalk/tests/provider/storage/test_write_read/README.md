# test_write_read

`LocalStorage.write_text` + `read_text` 的最基本契约 —— 写进去拿得出来,缺失返回 `None`。

## 场景矩阵

| 测试函数 | 验证什么 |
|---|---|
| `test_write_then_read_roundtrip` | 写文本然后读出来,内容完全一致 |
| `test_read_missing_returns_none` | 没写过的 key,`read_text` 返回 `None`(不抛错) |
| `test_write_creates_parent_dirs` | 多层路径(`a/b/c/file`)能成功写,即使父目录不存在 |
| `test_write_overwrites_existing` | 同一个 key 写两次,后一次覆盖前一次 |

## 覆盖的代码路径

- `provider/storage.py::LocalStorage.write_text`(原子写:tmp + rename)
- `LocalStorage.read_text`(missing → None,通过 `Path.exists()` 短路)
- 父目录 `mkdir(parents=True)` 的隐式自动创建

## 为什么 missing → None 而不是抛 FileNotFoundError

调用方很多时候是"看看在不在",抛错就要 `try/except` 包一层 noise。`None`
让"读不到"和"读到空字符串"清晰区分,业务里也好处理("没有就当首次")。
