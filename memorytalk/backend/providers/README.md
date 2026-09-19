# providers —— 存储介质的原语

两族基类,只有介质操作、没有业务(设计:[provider.md](../../../docs/designs/v5/provider.md))。业务层的仓储(`services/*/repo.py`)按族各写一份实现,同族之内换介质(LocalFS → S3、SQLite → MySQL)仓储不动。

| 文件 | 重点 |
|---|---|
| `__init__.py` | `load_store(home)`:按 `MEMORY_TALK_STORE`(`fs` 默认 / `sqlite`)返回一个 provider 实例 |
| `fs.py` | `FileSystemProvider` 基类:`read` / `write`(整体替换,原子)/ `append` / `delete` / `exists` / `list(prefix)` / `stat` / `local_path`;`LocalFS(root)` 是唯一实现,路径都相对 root |
| `db.py` | `DatabaseProvider` 基类:自己写的一层薄 ORM——`Column`(`==` / `in_` / `is_null` / `asc` / `desc` 构造条件和排序)、`Table`、链式的 `select().where().order_by().limit().all() / one()`、`insert().values().run()`、`update().set().run()`、`delete().run()`、`transaction()`、`ensure_table()`。方言只有三个点:`_placeholder` / `_type` / `_execute`。`SQLite` 是第一个实现;JSON 列用 `JSON` 抽象类型,存取时 `_encode` / `_decode` |

collections 不走这里:它是一个 git 仓库,原语在 `services/collections/git.py`。
