# providers —— 存储介质的原语

两族基类,只有介质操作、没有业务(设计:[provider.md](../../../docs/designs/v5/provider.md))。业务层的仓储(`services/*/repo.py`)按族写实现,同族之内换介质(LocalFS → S3、SQLite → MySQL)仓储不动。work 只用数据库族(`works.db` / `worktrace.db`);users / auth 两族都有。

| 文件 | 重点 |
|---|---|
| `__init__.py` | `load_store(home)`:按 `MEMORY_TALK_STORE`(`fs` 默认 / `sqlite`)返回一个 provider 实例(给 users / auth 用;work 的两个库由 `StoreService` 直接开 `SQLite`) |
| `fs.py` | `FileSystemProvider` 基类:`read` / `write`(整体替换,原子)/ `append` / `delete` / `exists` / `list(prefix)` / `stat` / `local_path`;`LocalFS(root)` 是唯一实现,路径都相对 root |
| `db.py` | `DatabaseProvider` 基类:自己写的一层薄 ORM——`Column`(`==` / `!=` / `in_` / `is_null` / `is_not_null` / `asc` / `desc` 构造条件和排序;`col + n` / `col - n` 是 SET 里的表达式,挪位置、计数器 +1 用)、`Table`(表级选项:`primary_key=(…)` 组合主键、`indexes=[(…)]` 多列索引;单列主键照旧 `Column(primary=True)`)、链式的 `select().where().order_by(多个).limit().all() / one()`、`insert().values().run()`、`update().set().run()`、`delete().run()`、`transaction()`(持锁,嵌套只算深度,没有 savepoint)、`ensure_table()`。方言只有三个点:`_placeholder` / `_type` / `_execute`。`SQLite` 是第一个实现;JSON 列用 `JSON` 抽象类型,存取时 `_encode` / `_decode`;bool 列读回 bool |

metas 不走这里:它是一个 git 仓库,原语在 `services/metas/git.py`。
