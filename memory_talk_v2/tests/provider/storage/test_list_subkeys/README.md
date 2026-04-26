# test_list_subkeys

`list_subkeys(prefix)` —— 递归列出某 prefix 下所有"文件"key,排好序。
sessions/cards/links 的 iter_keys/iter_docs 全靠这一个原语支撑。

## 场景矩阵

| 测试函数 | 验证什么 |
|---|---|
| `test_list_empty_prefix_returns_empty` | prefix 不存在时返回 `[]`(不抛错) |
| `test_list_returns_relative_keys` | 返回的 key 是 prefix 下的相对路径,使用 `/` 分隔 |
| `test_list_is_recursive` | 多层目录里的所有文件都被列出来,不只一层 |
| `test_list_skips_directories` | 返回值里只有"文件"key,目录本身不会出现 |
| `test_list_is_sorted` | 输出按字典序排好,迭代有确定顺序 |

## 覆盖的代码路径

- `provider/storage.py::LocalStorage.list_subkeys`(`rglob("*")` + `is_file()` 过滤)
- 路径分隔符规整化(Windows 也要用 `/`)
- 排序,确保 rebuild 等下游迭代是 deterministic 的

## 为什么不返回目录

S3 没有目录,只有 object key。这层接口对齐 S3 语义:列的就是"对象"。
本地 FS 上目录是隐含的(从 key 里能看出层级),但不作为单独条目。
