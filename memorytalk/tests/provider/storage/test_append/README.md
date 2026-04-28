# test_append

`LocalStorage.append_text` —— jsonl 这种"逐行追加"场景的核心契约。

## 场景矩阵

| 测试函数 | 验证什么 |
|---|---|
| `test_append_to_new_creates_file` | 文件不存在时,`append_text` 等价于 write,文件被创建 |
| `test_append_accumulates` | 多次 append 的内容按顺序串联(O_APPEND 语义)|
| `test_append_creates_parent_dirs` | 跟 `write_text` 一样自动创建父目录 |
| `test_append_then_read_roundtrip` | append 出来的内容能用 `read_text` 完整读回 |

## 覆盖的代码路径

- `provider/storage.py::LocalStorage.append_text`(O_APPEND 模式)
- 与 `read_text` 的协作:append 的内容能通过同一接口读回

## 为什么 append 是 O_APPEND 而不是 read+concat+write

本地文件系统下 O_APPEND 对单次小写入是原子的,多进程并发也安全。
S3 没有原生 append,未来如果要做 S3 适配,这一步会变成 `read+concat+put`,
但 protocol 层不变:同一个 `append_text(key, content)` 调用。
