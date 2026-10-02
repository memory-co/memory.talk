# provider —— 存储介质的两族基类:文件系统型、数据库型(v5 设计)

> **状态:框架稿,部分实施。** 已有的实现只有 `LocalFS`(文件系统族)和 `SQLite`(数据库族),代码在 `memorytalk/backend/providers/`;OSS / S3 / MySQL / PostgreSQL 还没写,`MEMORY_TALK_STORE` 只认 `fs` / `sqlite`。work 只用数据库族(两个 sqlite,[work-store.md](work-store.md)),users / auth 两族都有。本篇立 **provider** 这层抽象:它是**介质原语**,和业务无关。两族、两个基类——**文件系统型**(本地文件系统、OSS、S3……)和**数据库型**(SQLite、MySQL、PostgreSQL……)。具体介质各自实现自己那一族的基类;上层业务(work / user 的记录)按族写一份仓储,用 provider 的原语落地。provider 里**没有** work、user、document 这类词——那是业务,和底层无关。总定位见 [README.md](README.md)。

相关:
- v5 metas store(认知层的介质就是 git,不在本篇范围): [metas/store.md](metas/store.md)
- v5 user / work(用 provider 落地的两类业务记录): [user.md](user.md) / [work.md](work.md)

---

## 1. 一句话:provider 只回答「字节怎么存」,不回答「存的是什么」

```
业务层     WorkService / user 那套 / manager 投递          ← 只认业务仓储的接口,不知道介质
仓储层     UserRepo(fs 版 / db 版)   WorkRepo / TraceRepo(只有 db 版)  ← 业务概念在这里:users/<name>.json、works 表、spans 表
provider   FileSystemProvider 基类   DatabaseProvider 基类  ← 介质原语:路径 + 字节 / 表 + 链式查询(方言在里面)
介质       LocalFS / OSS / S3        SQLite / MySQL / PostgreSQL
```

三条边界:

- **provider 不认识业务。** 它的接口里只有路径、字节、表、列、链式查询——没有 work、没有 user、没有 document、没有 log。
- **两族是真的不一样,所以两个基类,不硬合成一个。** 文件系统给的是「路径 + 字节」,数据库给的是「表 + 链式查询」;假装它们一样,结果是在文件系统上模拟查询(慢到不可用)或在数据库上模拟路径(根本没有)。
- **同一族之内可换,上层零感知。** 本地文件系统换成 S3,数据库从 SQLite 换成 MySQL——仓储不动;换族(文件系统 → 数据库)是换一份仓储实现,业务层不动。

---

## 2. 文件系统型:`FileSystemProvider`

**一族**:本地文件系统、OSS、S3、以及任何「按路径存字节」的东西。基类定的是这一族的公共原语:

```python
class FileSystemProvider:
    def read(self, path: str) -> bytes | None
    def write(self, path: str, data: bytes) -> None        # 整体替换;对调用方而言是原子的(要么旧的要么新的)
    def append(self, path: str, data: bytes) -> None       # 追加到末尾
    def delete(self, path: str) -> None
    def exists(self, path: str) -> bool
    def list(self, prefix: str) -> list[str]               # 前缀下的全部路径
    def stat(self, path: str) -> Stat | None               # size / mtime
    # 能力(不是每个实现都有):
    def local_path(self, path: str) -> Path | None         # 本机真实路径;只有 LocalFS 有
    def watch(self, prefix: str, callback) -> Handle | None
```

| 实现 | `write` | `append` | `local_path` | 备注 |
|---|---|---|---|---|
| **LocalFS**(默认) | 临时文件 + rename | `open(a)` | 有 | `MEMORY_TALK_STORE=fs` 时 `users/`、`auth/tokens/` 用的就是它 |
| **S3 / OSS** | PutObject(天然整体替换) | **对象存储没有原生 append**:实现上要么读回 + 拼接 + 写回(小文件可以),要么一行一个对象再按前缀 list——由实现选,基类只要求语义 | 没有 | 适合把只增的痕迹(轨迹、对话)和 blob 放远端 |

`local_path` 是这一族里唯一的能力差异:agent 的把手、attach 脚本、人 `cat` 需要一个本机路径;远端对象存储给不了。仓储层要用它时先问一句,没有就退回 `read`。

---

## 3. 数据库型:`DatabaseProvider`

**一族**:SQLite、MySQL、PostgreSQL、以及任何「表 + 查询」的东西。基类**做到 ORM 这一层**:对外释放的是表定义和**链式的查询构造**,不是 SQL 字符串——方言差异(占位符、自增、JSON 列、`RETURNING`、`LIMIT` 语法)全部在 provider 内部吸收,仓储层**一行 SQL 都不写**。

```python
class DatabaseProvider:
    # 表:仓储层用列声明表,provider 负责建 / 升级(幂等)
    def table(self, name: str, *columns: Column,                   # Column(name, type, primary=…, index=…, nullable=…)
              primary_key: tuple[str, ...] = (),                   # 组合主键(这几列强制 NOT NULL);单列主键仍用 Column(primary=True)
              indexes: list[tuple[str, ...]] = ()) -> Table       # 多列索引;单列索引仍用 Column(index=True)
    # 查询构造:链式,最后 .all() / .one() / .run() 才落地成方言 SQL 执行
    def select(self, table: Table) -> Select      # .where(col == v, col.in_(…), col.is_null() / .is_not_null(), …).order_by(a.asc(), b.desc()).limit(n).offset(m).all() / .one()
    def insert(self, table: Table) -> Insert      # .values(**row).run() → 主键
    def update(self, table: Table) -> Update      # .where(…).set(**changes).run() → 受影响行数;set(pos=t.c.pos + 1) = 原地加减
    def delete(self, table: Table) -> Delete      # .where(…).run()
    def transaction(self) -> ContextManager       # 一组操作要么全成要么全不成
```

仓储层的写法长这样,在三种数据库上一字不改:

```python
works = db.table("works", Column("id", str, primary=True), Column("parent", str, index=True, nullable=True),
                 Column("created_by", str, index=True), Column("status", str), Column("data", JSON))
db.select(works).where(works.c.created_by == user, works.c.status != "archived").order_by(works.c.created_at.desc()).all()
db.update(works).where(works.c.id == wid, works.c.version == expect).set(status="archived", version=expect + 1).run()
```

| 实现 | 备注 |
|---|---|
| **SQLite** | 单文件,零依赖;单机想要查询能力时的第一选择 |
| **MySQL / PostgreSQL** | 多机共用一个实例、多写者时用;连接串从环境变量来(行为不来自文件,同 `*muxd` 的规矩) |

要点:

- **列类型是一小组抽象类型**(`str` / `int` / `bool` / `float` / `datetime` / `JSON` / `text`),每个实现映射成自己的原生类型,读回来还是那个 Python 类型(sqlite 里 bool 存成 0 / 1,读回 `True` / `False`);仓储层不见 `VARCHAR(255)` 这种东西。
- **组合主键和多列索引在表上声明**(`primary_key=` / `indexes=`):work 的 `work_columns` 主键是 (`work_id`, `number`),`worklets` 有 (`work_id`, `column_number`, `position`) 的索引([work-store.md §7](work-store.md))。只做普通索引,不做 UNIQUE——要「同一列里位置不重复」由仓储在一个事务里挪位置来守,sqlite 在 `position = position + 1` 时逐行查重会误报。
- **条件、排序、分页都是构造出来的对象**,不是拼字符串——所以没有注入问题,也没有方言问题。
- **不做关系映射**(没有对象图、没有懒加载):它是查询构造器 + 表定义,够仓储层用;真要 ORM 的对象那一半,仓储层自己在上面包。
- **底下用什么实现构造器**是实现细节:自己写一层薄的,或者包 SQLAlchemy Core——都行,基类的面不变。

---

## 4. 仓储层:业务概念住在这里,按族各写一份

> **work 已经只留 db 版**([work-store.md](work-store.md)):`WorkRepo`(works.db:节点、列、工作单元登记(连同摆在哪)、收件箱)+ `TraceRepo`(worktrace.db:段、点、agent 的对话),各用一个 `SQLite` provider,不看 `MEMORY_TALK_STORE`。现在按族各一份实现的只剩 user / auth(`UserRepo` / `TokenRepo`)。

work / user 的记录(work 节点、列、工作单元登记、收件箱、轨迹(含 agent 的对话);user 的档案、登录态)是**业务**。业务层需要的操作定成一个接口——它长什么样是业务层的事,provider 不管;然后**按族各实现一份**(work 那几行只有 db 版):

| | fs 版仓储(用 `FileSystemProvider`) | db 版仓储(用 `DatabaseProvider`) |
|---|---|---|
| user 档案 | `users/<name>.json` | `users` 表,一行 |
| 登录态(token 登记) | `auth/tokens/<sha256>.json` | `auth_tokens` 表,一行 |
| work 节点 / manager / 谁在看 / 计数器 | —(上一版是 `works/<id>/work.json` 等文件,已删) | `works` 表,一行 |
| 列和位置 | —(上一版整份存在一个 JSON 文件里) | `work_columns` 表 + `worklets` 的位置列 |
| 工作单元登记 | —(上一版是 `worklets.json`) | `worklets` 表,一行 |
| 收件箱 | —(上一版是 JSONL) | `inbox` 表,自增 `seq` |
| 轨迹(含 agent 的对话) | —(上一版是 `events` / `rounds` 的 JSONL) | worktrace.db 的 `spans` / `points` 表(现在另有 `rounds` 表,按 [work-node.md](work-node.md) 改完并进 `points`) |
| 「按父列子」「按 created_by 列」 | —(上一版是 `list` 前缀 + 读每个 `work.json` 在内存里过滤) | `select(works).where(works.c.parent == pid)`,走索引 |
| 把路径交给外部进程(agent 读自己的对话) | `local_path`(LocalFS 有;S3 没有 → 退回 `read`) | 没有路径;通过仓储读(agent 的对话就是这样:从平台记录文件读出来进 `worktrace.db`,接口从表里读) |

两点要说清:

- **业务接口一份,实现两份**——不是一份实现套两种 provider。因为两族的「自然写法」不同:文件系统就该整文件读写,数据库就该用查询构造器按条件取;硬用一份代码适配两族,就是在其中一族上写别扭的代码。
- **同一族之内不用再分**:fs 版仓储对 LocalFS 和 S3 一视同仁(只在 `local_path` 上问一句);db 版仓储对 SQLite 和 MySQL 一视同仁(方言在 provider 的 ORM 层里吸收,仓储层不写 SQL)。

---

## 5. 选哪个:配置定,业务层不感知

```
MEMORY_TALK_STORE=fs            (默认)  → LocalFS,根在 MEMORY_TALK_HOME
MEMORY_TALK_STORE=s3   + bucket / 凭证  → S3(还没写)
MEMORY_TALK_STORE=sqlite + 文件路径     → SQLite(路径 MEMORY_TALK_SQLITE,默认 <home>/memory.sqlite)
MEMORY_TALK_STORE=mysql  + DSN          → MySQL(还没写)
```

启动时按配置装配:选族 → 选实现 → 建对应的仓储 → 交给业务层。业务层拿到的是仓储接口,不知道底下是文件还是表。**这个开关现在只管 users / auth**;work 固定是两个 sqlite(`MEMORY_TALK_WORKS_DB` / `MEMORY_TALK_WORKTRACE_DB`,默认 `<home>/works.db` / `<home>/worktrace.db`)。

**混搭**:某些流可以指定另一个 provider——典型是大的只增流(比如 agent 的对话):主存储用 MySQL,它仍用 LocalFS(大、只增、要给 agent 一个路径)。这是装配时的事,仓储层收到两个 provider,业务层仍只看到一份接口。(work 现在是另一种拆法:「现在」和「经过」各一个 sqlite,agent 的对话跟着轨迹进 `worktrace.db`,见 [work-store.md §1](work-store.md)。)

---

## 6. 和 metas 的边界

metas 的介质就是 git([metas/store.md](metas/store.md)),**不走 provider**。git 需要本机文件系统,这是硬要求。

但 provider 在 metas 那边有一个天然的位置:**blob 外置**。collectbase 把二进制放到 `blob/` 目录、原地留软链;那个 `blob/` 正是一个 `FileSystemProvider` 该管的东西——本地时是 LocalFS,想把大文件放远端时换 S3,metas 仓库里的软链不变。这是将来做 blob 外置时顺手的事,本篇记一笔。

---

## 7. 这篇有意不定的事

- ~~user 资料放哪~~:已定——user 是注册的实体,档案走仓储(fs `users/<name>.json` / db `users` 表),和 work 一样按族各一份实现。

- **对象存储的 `append` 怎么做**:读回拼接(简单,小文件够用)还是一行一对象(可扩展,list 成本高)。先按前者;agent 对话这种大流本来就建议留 LocalFS。
- **`watch` 要不要进基类**:前端实时性会要;LocalFS 用 inotify,S3 没有,数据库看实现。先作为能力,不进必须项。
- **db 版仓储的表结构**:一张宽表省事,每类一张表查询好;倾向每类一张表——既然选了数据库就把它的长处用上。
- **查询构造器自己写还是包 SQLAlchemy Core**:自己写面最小、零依赖,但要自己吸收三种方言;包 SQLAlchemy 省事、方言现成,多一个依赖。倾向先包,面收在基类里,将来想换随时换。
- **多写者**:LocalFS 假设单写者(进程内锁);数据库天然多写者。换到数据库后业务层要不要放开并发——放开就得处理 work 树上的竞争,先不。
- **迁移**:两份仓储都实现 `dump()` / `load()`,介质之间搬家就是导出再导入。格式定成什么(JSONL 一行一记录?)等要搬的时候再定。
