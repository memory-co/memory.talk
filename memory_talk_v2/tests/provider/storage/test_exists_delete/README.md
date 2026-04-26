# test_exists_delete

`exists` 和 `delete` —— head/delete 这一对原语。

## 场景矩阵

| 测试函数 | 验证什么 |
|---|---|
| `test_exists_after_write` | 写过的 key,`exists` 为 True |
| `test_exists_for_missing_is_false` | 没写过的 key,`exists` 为 False(不抛错) |
| `test_delete_removes_key` | 写 → delete → exists 变 False,`read_text` 返回 None |
| `test_delete_missing_is_noop` | 删不存在的 key 不抛错 —— retention 等场景需要这种幂等性 |

## 覆盖的代码路径

- `provider/storage.py::LocalStorage.exists`(`Path.exists()` 直查)
- `LocalStorage.delete`(`unlink()` + 吞掉 `FileNotFoundError`)

## 为什么 delete 对 missing 静默

`SearchLogStore.apply_retention()` 这种批量删除场景,可能会删一个上一次刚被
其他进程删掉的文件。要求调用方先 `exists` 再 `delete` 是 race-prone(TOCTOU);
让 delete 自己吞 FNF 是更鲁棒的做法。
