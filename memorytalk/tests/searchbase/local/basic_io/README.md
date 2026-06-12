# basic_io — 核心读写 round-trip

## 这个场景在测什么

`LocalSearchBackend` 最普通的使用姿势 —— `upsert` 写一些 doc,`search`
能找回来,`count` 数对。同时锁住两条边界约束:

1. **文本长度上限**:超过 `max_text_length` 的 doc 整条 `upsert` 失败
   (不偷偷截断),这样调用方的"我以为我存进去了"不会跟"我搜不到"互相欺骗。

2. **声明 schema 锁住列类型**:第一行写 `score=None` 不会让 `score` 这一列
   退化成 string —— 类型来自 `_schema_for` 的声明,不是首行推断。

## 不在这测什么

- 分块(`auto_split`)走 `auto_split/`
- 维护循环 / health 走 `compaction/`
- EMFILE 异常路径走 `emfile_recovery/`
- 日志文件落点走 `file_logging/`

## fixture 来源

- `backend` (`local/conftest.py`) — 基本 `cards` collection
- `make_backend` + `data_root` (`local/conftest.py` / `tests/conftest.py`)
  — 自定义 `max_text_length` 或带字段的 collection
