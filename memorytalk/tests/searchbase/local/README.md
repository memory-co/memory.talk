# searchbase/local 测试 — 按场景组织

每个子目录是**一个场景**:有自己的 `README.md` 写清"在测什么 / 不在
测什么 / 用哪些 fixture",有自己的 `test.py` 装测试用例。多个相关的
单元测试合并在一个场景下,跟"按代码模块切文件"的旧习惯解耦。

## 场景一览

| 目录 | 测什么 |
|---|---|
| [`basic_io/`](basic_io/) | 核心 upsert / search / count round-trip + 文本长度上限 + 声明 schema 类型不被首行 null 污染 |
| [`auto_split/`](auto_split/) | 长 doc 切块对调用方完全不可见(count / search / delete 都按逻辑 doc) |
| [`compaction/`](compaction/) | Maintenance 生命周期 + 周期 compaction + 单跳异常不杀循环 + 错误字段清零 + health 6 字段 |
| [`emfile_recovery/`](emfile_recovery/) | search 撞 EMFILE 后:counter 推进 + 并发复用一次 recovery + LanceDB 真的重连 + known set 自刷新 |
| [`file_logging/`](file_logging/) | 三类操作各自落 `maintenance.log` / `query.log` / `index.log`,setup 幂等,propagate=False,互不污染 |
| [`fts_self_heal/`](fts_self_heal/) | FTS index 盘上残缺(文件丢失但 manifest 占名)时 search 自动重建而不是 500(1.0.0 升级事故回归测试) |

## 共享 fixture

`conftest.py` 提供两个跨场景常用的 fixture:

- `backend` —— 普通 `LocalSearchBackend` + 一个 `cards` collection
- `index` —— 原始 `CollectionIndex` + `things` collection,给需要直接
  构造 `Maintenance(index, ...)` 控制 interval 的场景用
- `make_backend(config, *, collections, ...)` —— 自定义 collection /
  `max_text_length` / `log_dir` 时调用的工厂函数

## 加新场景

1. 新目录 `tests/searchbase/local/场景名/`
2. 写 `README.md`:**测什么 / 不测什么 / fixture 来源**
3. 写 `test.py`:测试本体
4. 不需要在任何 index 里登记 —— pytest 自动收集
