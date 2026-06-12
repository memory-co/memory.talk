# migration 模块 + migrations 内容

把所有持久化层的 schema 演化收敛到一处 —— SQLite **和** searchbase 都走同一套**有版本号的迁移框架**,而不是各自散落在 `repository/schema.py:_additive_migrations` 和某个 ad-hoc upgrade 脚本里。

两个模块,职责分开:

| 模块 | 性质 | 类比 |
|---|---|---|
| `memorytalk/migrations/` | **内容**:每个版本目录,放该版本的 init + up 文件 | `memorytalk/schemas/` —— 内容声明,业务感知 |
| `memorytalk/migration/` | **框架**:Runner / State / 发现机制 | Django 的 `django.db.migrations` —— 引擎,业务无关 |

> **状态:已设计,未实施。** 本文是落地前的方案对齐。

跟其它 works 文档的关系:
- [`searchbase-extraction.md`](searchbase-extraction.md) 的下游 —— searchbase 故意不动 schema 演化,留给 migration 兜底
- 替代 `repository/schema.py:_additive_migrations` 的零散 ALTER 流程 —— 把它升级成"有版本号 + 有 init/up 区分"的正式框架
- 跟 [`index-backfill.md`](index-backfill.md) 正交:backfill 解决"数据丢了从 source-of-truth 重灌",migration 解决"schema 变了原地 ALTER"

## 动机

之前讨论过两条路:

| | 当时考虑 | 否决理由 |
|---|---|---|
| Instance versioning(`v1/cards/` 不同目录) | 大版本隔离,回滚便利 | memory.talk 是本地单用户工具,**没有 zero-downtime / side-by-side serving 需求**;instance 提供的运维便利换不来结构性能力,反而把 0.8.1 → 0.9 兼容搞复杂 |
| 一锅 ad-hoc 迁移脚本(`upgrade-searchbase` CLI) | 实现简单 | 第二次迁移时回头看,没有版本号的"我跑过哪些"很难推理 |

最终方案:**Alembic / Flyway 那套版本化 migration**,但**同时管 database 和 searchbase 两个子系统**,因为 memory.talk 的 schema 演化经常是双轴联动(给 cards 加字段往往两边都要改)。

## 范围

**做**:

- 同一个版本号空间(`v1` / `v2` / `v3` / ...)管理 SQLite 和 LanceDB 两个子系统的 schema 演化
- 每个版本提供两份文件:**init**(从零建到这个版本的全量)+ **up**(从上一版到本版的增量)
- 启动时自动决定走哪条路 —— 新安装走 init,升级走 up
- 跟踪"我跑过哪些 (version, subsystem)",失败 abort
- 给 0.8.1 → 0.9 这条特殊路径一个 baseline,**自动检测旧布局并 catch up**

**不做**:

- **不做** 数据 regeneration(换 embedding 模型 / 重分词)。这些是 user-intent flow,独立路径
- **不做** down migration / 自动回滚。**单向。** 失败靠备份恢复
- **不做** 跨语言 / 跨工具的 migration 格式互通 —— 这是 memorytalk 内部框架,不假装通用

## 最终结构

```
memorytalk/
  migrations/                          ← 内容(跟 schemas/ 同级)
    __init__.py
    v1/
      __init__.py
      init_database.py                 SQLite 全量 schema(给 fresh install)
      init_searchbase.py               LanceDB 全量 schema(给 fresh install)
      up_database.py                   SQLite 增量(给从 0.8.1 升过来的)
      up_searchbase.py                 LanceDB 增量(给从 0.8.1 升过来的)
    v2/
      init_database.py                 v1 全量 + v2 变化
      init_searchbase.py
      up_database.py                   v1 → v2 的增量
      up_searchbase.py
    v3/...

  migration/                            ← 框架
    __init__.py
    _types.py                          MigrationContext / 版本号 / subsystem 枚举
    runner.py                          MigrationRunner:扫 migrations/,定路径,执行
    state.py                           applied_migrations 表的读写
    discover.py                        从 migrations/ 目录读出所有版本

  searchbase/_types.py                 加 AdminBackend(Protocol) ← 新增
  searchbase/local/_admin.py           LocalAdminBackend 实现 ← 新增
  searchbase/local/backend.py          LocalSearchBackend.admin() ← 新增
  repository/schema.py                 _additive_migrations 整段删 ← 内容搬到 migrations/v1/up_database.py
```

## 子系统拆分:为什么是 database + searchbase

memorytalk 现在有两个独立的 schema 演化轴:

| 子系统 | 存储 | 当前演化机制 | 迁移到 migrations/ 后 |
|---|---|---|---|
| database | SQLite | `repository/schema.py:_additive_migrations` 一锅 ALTER | `migrations/vN/{init,up}_database.py` |
| searchbase | LanceDB | 没有(声明即冻结) | `migrations/vN/{init,up}_searchbase.py` |

未来如果出现第三个持久化层(假设的 `relations.db` / 外部远端 backend / 等),就加 `init_xxx.py` + `up_xxx.py`,Runner 自动发现。

## init vs up:语义和触发条件

这是这一版设计的核心。**每个版本都有两份文件**,**只用其中一份**,看用户当前状态决定:

| 用户状态 | 跑什么 | 体感 |
|---|---|---|
| 全新安装(没 `applied_migrations` 表 + 没旧数据) | **`init_*.py` for LATEST version** ←(只跑最新版的 init,跳过所有中间的 up) | 一次性建好,启动快 |
| 升级(`applied_migrations` 有记录,落后于最新) | **每缺一个 version 跑对应的 `up_*.py`**,按版本顺序 | catch up,可能要几秒到几分钟 |
| 0.8.1 升上来(有数据但没 `applied_migrations` 表) | 视作"从 v0 升上来",从 `v1/up_*.py` 开始挨个跑 | 同上 |

### 为什么不把 init 删掉、只留 up?

只留 up 的话,**全新安装要按 v1 → v2 → ... → v_latest 顺序跑所有 up**。当版本号涨到 15 时,新用户启动时要顺序跑 15 个 up,慢 + 心智重 + 错误面积大。

init 提供一个 shortcut:**"我现在就在 latest"**,一次到位。代价是**每次加一个版本要同时更新 `init` 和 `up`**(全量 + 增量),写者负担稍重。

### 为什么不把 up 删掉、只留 init?

只留 init 的话,**升级用户没法接力** —— init 假设你是从零开始的,但已经有数据的人不能"从零开始"。所以 up 是必须的。

### 老 init(v1/init_*)还会被跑吗?

**只有最新版本的 init 会被 Runner 真正调用。** 老版本的 init 仍然保留在仓库里,作为**那个版本的 schema 文档**(读代码就能看出 v3 当时长什么样)。

如果哪天想"装个 v3 历史快照来调试 bug",可以**手动**指定 `init_v3` 跑,但 Runner 默认不会。

## 文件长什么样

### `migrations/v1/init_database.py`(SQLite 全量 schema)

```python
"""Database schema at v1 — fresh-install baseline.

Idempotent (CREATE TABLE IF NOT EXISTS). Runner 调一次,之后通过
applied_migrations 标记跳过。
"""

async def run(conn):
    # Sessions
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id  TEXT PRIMARY KEY,
            source      TEXT NOT NULL,
            ...
        )
    """)
    # Cards
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            card_id     TEXT PRIMARY KEY,
            insight     TEXT NOT NULL,
            ...
        )
    """)
    # ... 所有 v1 的表
    await conn.commit()
```

### `migrations/v1/init_searchbase.py`(LanceDB 全量 schema)

```python
"""Searchbase schema at v1 — fresh-install baseline."""

async def run(admin):
    await admin.create_collection("cards", schema={
        "fields": {},   # generic: just id/text/vector
    })
    await admin.create_collection("rounds", schema={
        "fields": {"session_id": "str", "idx": "int", "role": "str"},
        "auto_split": True,
    })
```

### `migrations/v1/up_database.py`(0.8.x → v1 SQLite 增量)

```python
"""Database upgrade: 0.8.x → v1.

吃掉原来 repository/schema.py:_additive_migrations 里的所有 ALTER。
全部幂等(IF NOT EXISTS / 检测后跳过)。
"""

async def run(conn):
    # applied_migrations 表本身要在这里建,Runner 才能记录这条 migration
    # 已成功。chicken-and-egg 在 Runner 层有特别处理(见下方)。
    
    # 例:0.8.x → v1 加 sessions.tags 列
    cols = await _columns(conn, "sessions")
    if "tags" not in cols:
        await conn.execute(
            "ALTER TABLE sessions ADD COLUMN tags TEXT NOT NULL DEFAULT '{}'"
        )
    # ... 其余 _additive_migrations 内容
    await conn.commit()
```

### `migrations/v1/up_searchbase.py`(0.8.x → v1 LanceDB 增量)

```python
"""Searchbase upgrade: 0.8.x → v1.

0.8.x 旧 LanceDB schema:
  cards   = (card_id, text, vector)
  rounds  = (session_id, idx, role, text, vector)

v1 schema:
  cards   = (id, text, vector)                                  ← card_id 重命名
  rounds  = (id, _base_id, _chunk, session_id, idx, role, text, vector)
                  ↑ id = f"{session_id}:{idx}"
                  ↑ _base_id = id     (一行 = 一个完整 doc,_chunk=0)
                  ↑ _chunk = 0
"""

async def run(admin):
    collections = await admin.list_collections()

    if "cards" in collections:
        cols = await admin.list_columns("cards")
        if "card_id" in cols and "id" not in cols:
            await admin.rename_column("cards", "card_id", "id")

    if "rounds" in collections:
        cols = await admin.list_columns("rounds")
        if "id" not in cols:
            await admin.add_column(
                "rounds", "id", type_="str",
                compute=lambda r: f"{r['session_id']}:{r['idx']}",
            )
        if "_base_id" not in cols:
            await admin.add_column(
                "rounds", "_base_id", type_="str",
                compute=lambda r: f"{r['session_id']}:{r['idx']}",
            )
        if "_chunk" not in cols:
            await admin.add_column(
                "rounds", "_chunk", type_="int", default=0,
            )
```

## 契约:`AdminBackend`(`searchbase/_types.py` 新增)

migration 层调用 searchbase 时需要的低层操作。**不在 public `SearchBackend` 端口里** —— 业务 service 代码永远不调 admin。

```python
class AdminBackend(Protocol):
    async def list_collections(self) -> list[str]: ...
    async def list_columns(self, collection: str) -> list[str]: ...

    async def add_column(
        self, collection: str, column: str, type_: str,
        *, default=None,
        compute: Callable[[dict], object] | None = None,
    ) -> None: ...

    async def rename_column(
        self, collection: str, old: str, new: str,
    ) -> None: ...

    async def drop_column(
        self, collection: str, column: str,
    ) -> None: ...

    async def create_collection(
        self, name: str, schema: dict,
    ) -> None: ...

    async def drop_collection(self, name: str) -> None: ...

    async def copy_rows(
        self, src: str, dst: str,
        *, transform: Callable[[dict], dict] | None = None,
        where: str | None = None,
    ) -> int: ...
```

`SearchBackend` 端口加一个 `admin() -> AdminBackend` 方法返回。

数据库那边不需要类似的端口 —— 直接用 `aiosqlite.Connection`。

## State 跟踪

**一个 JSON 文件**:`data_root/migrations_state.json`。shape:

```json
{
  "schema_version": 1,
  "applied": [
    {
      "version": "v1",
      "subsystem": "database",
      "method": "up",
      "applied_at": "2026-06-08T03:42:18Z",
      "duration_ms": 127
    },
    {
      "version": "v1",
      "subsystem": "searchbase",
      "method": "up",
      "applied_at": "2026-06-08T03:42:19Z",
      "duration_ms": 845
    }
  ]
}
```

`schema_version` 是**state 文件自身的格式版本号**(不是 migration 版本),给以后这个 JSON 格式真的要演化时留个口子。

**写入方式**:写 `migrations_state.json.tmp` → `os.replace()` 原子覆盖,避免半截写入。memory.talk 是单进程跑的,不需要锁。

为什么 JSON 而不是 SQLite:

- 内容就几行,SQLite 是过度工程 —— 起 connection、建表自己又是个 chicken-and-egg
- 文件可以直接 `cat` / `jq` 看,运维诊断更直接
- 没有依赖。一个 `json.load` / `json.dump` 解决,框架代码更短
- 备份就是 `cp`,恢复就是 `cp` 回来

文件不存在 = 等同于 `applied = []`(全新状态)。损坏的话 Runner 报错 abort,让用户决定:删掉重跑(代价是所有 migration 都重跑一次,**所以约定每个 migration 必须幂等**)或者手动修。

## 运行时序(lifespan)

```python
@asynccontextmanager
async def lifespan(app):
    # 1. 准备底层 handle(打开但不要求 schema 对齐)
    conn = await aiosqlite.connect(config.db_path)
    backend = await LocalSearchBackend.create(...)   # 现在不传 name 了

    # 2. 跑 migration —— 这是关键步骤,所有 schema 推齐在这一步
    runner = MigrationRunner(
        db_conn=conn,
        admin=backend.admin(),
        state_path=config.migrations_state_path,
        migrations_pkg="memorytalk.migrations",
    )
    summary = await runner.run()
    _log.info(
        "migrations: applied=%d, skipped=%d, mode=%s",
        summary.applied, summary.skipped, summary.mode,
    )

    # 3. 此时所有 schema 都对齐了 latest,可以放心起 service
    app.state.db = SQLiteStore(conn, ...)
    app.state.searchbase = backend
    # ... sync / backfill / 等等

    yield
    # ... shutdown
```

## Runner 内部逻辑

```python
class MigrationRunner:
    async def run(self) -> Summary:
        # Step A: 读 state JSON(不存在 = 空 applied list)
        applied = self._state.load()       # list of {version, subsystem, ...}
        applied_set = {(a["version"], a["subsystem"]) for a in applied}
        versions = self._discover()        # ['v1', 'v2', 'v3']
        latest = versions[-1]
        subsystems = ("database", "searchbase")

        # Step B: 决定模式
        if not applied_set:
            if self._data_exists():
                mode = "upgrade_from_zero"   # 0.8.1 升上来,从 v1/up 跑
            else:
                mode = "init_latest"          # 全新装,直接 init latest
        else:
            mode = "catch_up"                 # 升级,从最高已应用版本之后跑

        # Step C: 执行 —— 每个 migration 成功后立刻 save,断点续传友好
        if mode == "init_latest":
            for sub in subsystems:
                await self._run_init(latest, sub)
                # 一次到位:这个 subsystem 的所有 version 全标 applied
                for v in versions:
                    self._state.mark(v, sub, method="init")
                self._state.save()   # atomic write
        else:
            for sub in subsystems:
                current = self._highest_applied(applied_set, sub)
                for v in versions_after(current, versions):
                    await self._run_up(v, sub)
                    self._state.mark(v, sub, method="up")
                    self._state.save()   # atomic write per migration

        return Summary(...)
```

**`_data_exists()`**:简单启发 —— `config.db_path` 存在 OR `config.vectors_dir` 下有数据 → 视作有旧数据。

## 失败语义

| 场景 | 行为 |
|---|---|
| `migrations_state.json` 不存在 | 视作 `applied = []`,跑模式判定(`init_latest` 或 `upgrade_from_zero`) |
| `migrations_state.json` 损坏(JSON parse 失败) | abort + 报错;让用户决定:删掉重跑(所有 migration 重跑一次,**幂等约定保证不破坏数据**)或者手动修 |
| `up_xxx.py` 跑到一半抛了 | abort。**`state.save()` 在每个 migration 成功后立刻调**,所以失败的那个不会被标 applied → 下次启动重跑这个 version 这个 subsystem;之前已成功的 version 不重跑 |
| `init_xxx.py` 跑到一半抛了 | 同上(虽然 init 模式下 `state.save()` 把整个 subsystem 一口气标完,所以中途失败 = 整个 subsystem 没标,下次完整重跑;idempotency 由 `CREATE TABLE IF NOT EXISTS` 保证不破坏数据) |
| state JSON 里有当前代码里**没有**的 version(比如 `v9` 应用了但代码只到 `v7`) | 警告日志 + 继续 → 用户**降级了代码**,应该自己处理(降级路径不在框架职责内) |
| 当前代码声明的 schema 跟磁盘 schema 不一致但没有对应 migration | 业务侧第一次 upsert 会撞到 schema mismatch → 由调用方报错 → 提示用户**写一个新 migration version** |

**核心约定:每个 `init_*.py` / `up_*.py` 的 `run()` 必须幂等。** 重启重跑不应该破坏数据。这条比"写 down migration"更可靠,因为 down 更难写对。

## 0.8.1 → 0.9 这条特殊路径

**就是 v1/up_*.py 的责任**,没有独立机制。

升级体验:

1. 用户 `pip install --upgrade memorytalk` 拿到 0.9
2. `memory.talk server stop && memory.talk server start`
3. lifespan 跑到 migration step,看到 `migrations_state.json` 不存在但 `~/.memory.talk/memory.db` 和 `~/.memory.talk/vectors/cards.lance/` 都在
4. 模式判定为 `upgrade_from_zero` → 从 `v1/up_database.py` + `v1/up_searchbase.py` 跑
5. `up_database`: 把 `_additive_migrations` 的 SQLite ALTER 都跑一遍(幂等,真没改动的就跳)
6. `up_searchbase`: 把 cards.card_id 重命名为 id,给 rounds 加 id/_base_id/_chunk 三列
7. 标 v1 已应用,继续启动
8. 用户体感:**重启慢了几秒,然后一切照旧**,**没有 rm -rf**,**没有 cards 丢失**

`INSTANCE_NAME = "v1"` 常量在 `service/searchbase_schema.py` 里**整个删掉**,`LocalSearchBackend.create(...)` 的 `name` 参数变成可选(默认空字符串 = flat 布局,跟 0.8.1 一致)。

## 怎么加新版本

写完 v2 的代码、决定要 bump 版本号时:

1. `mkdir memorytalk/migrations/v2/`
2. 写 4 个文件:
   - `init_database.py`:在 v1/init_database.py 基础上**加上 v2 的所有变化**(用全量描述 v2 应该长什么样)
   - `init_searchbase.py`:同上
   - `up_database.py`:只描述 v1 → v2 的**增量**(`ALTER TABLE`、新建表、等等)
   - `up_searchbase.py`:同上
3. **Runner 自动发现**,不用注册
4. 写测试:
   - up 从 v1 数据上跑得通,结果等价于 init 在 fresh DB 上跑
   - up 幂等(跑两次结果一样)

## 决策表

| 题目 | 选择 | 理由 |
|---|---|---|
| migrations 内容放哪 | **顶级 `memorytalk/migrations/`** 跟 schemas/ 同级 | 业务内容,跟"框架"区分;不该塞进 migration/ 这个工具模块 |
| migration 框架放哪 | **`memorytalk/migration/`**(单数) | Python 习惯:`xxx/` = 框架,`xxxs/` = 内容,Django 同样套路 |
| init 和 up 是否两个文件 | **两个都要** | init 给 fresh install 一次到位,up 给升级用户挨个加;只留任一个都会有死角 |
| init 是否每个版本都要 | **是,但只跑最新版** | 老版本 init 留作"那个版本 schema 长啥样"的快照文档,Runner 不调 |
| database 和 searchbase 共用版本号 | **是** | 一个版本 = 一份完整的"产品 schema 快照",`v3` 同时定义 v3 的 SQLite 表和 v3 的 LanceDB 表 |
| state 怎么存 | **`migrations_state.json` 一个 JSON 文件** | 内容就几行,SQLite 是过度工程;JSON 直接 `cat`/`jq` 查,无依赖,备份就是 `cp` |
| 失败回滚机制 | **无 down migration,靠备份** | down 难写正确,本地工具用户做备份成本可控 |
| `INSTANCE_NAME = "v1"` | **删** | instance 设计被这次决定整个废弃,数据回到 flat 布局,0.8.1 兼容自动达成 |
| `repository/schema.py:_additive_migrations` | **删,内容搬到 `migrations/v1/up_database.py`** | 同一套机制管两个子系统,代码只在一处 |

## 边界(显式不做)

| 不该做的事 | 谁来做 |
|---|---|
| 重新算 cards / rounds 的 embedding | user-intent flow(待设计:`memory.talk reembed --model new_model`) |
| 重新切 chunk(`max_text_length` 改了) | 同上 |
| 改 FTS 词典 / tokenizer | 同上 |
| 业务侧加新字段(`session.tags` / `card.tags` 之类) | 加新 migration version 同时改 `migrations/vN/init_database.py` + `up_database.py`(SQLite ALTER)和(必要时)`init_searchbase.py` + `up_searchbase.py`(LanceDB ALTER) |
| jsonl 文件 / cards/ 目录布局变化 | 文件层迁移通常零成本(读时兼容、写时新格式),不进 migration 框架 |
| 跨进程 / 多版本共存 | 显式不支持。一个时刻只有一份代码在跑,迁移完成前其它服务挂掉 |

## 待办(实施时按顺序)

| 步骤 | 改动 |
|---|---|
| 1 | `searchbase/_types.py`:加 `AdminBackend` Protocol |
| 2 | `searchbase/local/index.py`:加 low-level `rename_column / add_column / drop_column / list_columns` |
| 3 | `searchbase/local/_admin.py`(新):`LocalAdminBackend` 实现 |
| 4 | `searchbase/local/backend.py`:`LocalSearchBackend.admin()` 返回 admin |
| 5 | `migration/_types.py` + `migration/state.py` + `migration/discover.py` + `migration/runner.py` |
| 6 | `migrations/__init__.py` + `migrations/v1/{init,up}_{database,searchbase}.py` |
| 7 | `migrations/v1/up_database.py`:把 `repository/schema.py:_additive_migrations` 整段搬过来 |
| 8 | `repository/schema.py`:删 `_additive_migrations`(变成单纯 DDL 常量) |
| 9 | `api/__init__.py` lifespan:在 backend 创建之后、service 启动之前加 `runner.run()` |
| 10 | `config.py`:加 `migrations_state_path = data_root / "migrations_state.json"` |
| 11 | `service/searchbase_schema.py`:删 `INSTANCE_NAME`,`build_search_backend` 不再传 `name` |
| 12 | 测试:`tests/migration/`(框架本身)+ `tests/migrations/v1/`(baseline 端到端) |

预估改动 ~600 LOC + 测试。**搬家一次,以后每个 schema 变化只加一个 `migrations/vN/` 目录,模块结构 stable 下来。**
