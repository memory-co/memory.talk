# provider —— 存储介质的两族基类:文件系统型、数据库型(v5 设计)

> **状态:框架稿,未实施。** 本篇立 **provider** 这层抽象:它是**介质原语**,和业务无关。两族、两个基类——**文件系统型**(本地文件系统、OSS、S3……)和**数据库型**(SQLite、MySQL、PostgreSQL……)。具体介质各自实现自己那一族的基类;上层业务(work / user 的记录)按族写一份仓储,用 provider 的原语落地。provider 里**没有** work、user、document 这类词——那是业务,和底层无关。总定位见 [README.md](README.md)。

相关:
- v5 collections store(认知层的介质就是 git,不在本篇范围): [collections-store.md](collections-store.md)
- v5 user / work(用 provider 落地的两类业务记录): [user.md](user.md) / [work.md](work.md)

---

## 1. 一句话:provider 只回答「字节怎么存」,不回答「存的是什么」

```
业务层     WorkService / user 那套 / manager 投递          ← 只认业务仓储的接口,不知道介质
仓储层     WorkRepo(fs 版)   WorkRepo(db 版)               ← 业务概念在这里:work.json、rounds.jsonl、works 表
provider   FileSystemProvider 基类   DatabaseProvider 基类  ← 介质原语:字节、路径、行、SQL
介质       LocalFS / OSS / S3        SQLite / MySQL / PostgreSQL
```

三条边界:

- **provider 不认识业务。** 它的接口里只有路径、字节、表、行、SQL——没有 work、没有 user、没有 document、没有 log。
- **两族是真的不一样,所以两个基类,不硬合成一个。** 文件系统给的是「路径 + 字节」,数据库给的是「表 + 查询」;假装它们一样,结果是在文件系统上模拟查询(慢到不可用)或在数据库上模拟路径(根本没有)。
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
| **LocalFS**(默认) | 临时文件 + rename | `open(a)` | 有 | 今天 `~/.memory.talk/works/` 的那套纪律就是它 |
| **S3 / OSS** | PutObject(天然整体替换) | **对象存储没有原生 append**:实现上要么读回 + 拼接 + 写回(小文件可以),要么一行一个对象再按前缀 list——由实现选,基类只要求语义 | 没有 | 适合把 rounds 这类只增的痕迹和 blob 放远端 |

`local_path` 是这一族里唯一的能力差异:agent 的把手、attach 脚本、人 `cat` 需要一个本机路径;远端对象存储给不了。仓储层要用它时先问一句,没有就退回 `read`。

---

## 3. 数据库型:`DatabaseProvider`

**一族**:SQLite、MySQL、PostgreSQL、以及任何「表 + SQL」的东西。基类定的是这一族的公共原语:

```python
class DatabaseProvider:
    def execute(self, sql: str, params: Sequence = ()) -> int          # 写;返回受影响行数
    def query(self, sql: str, params: Sequence = ()) -> list[Row]      # 读
    def transaction(self) -> ContextManager                            # 一组语句要么全成要么全不成
    def ensure_schema(self, ddl: list[str]) -> None                    # 建表 / 升级,幂等
    dialect: str                                                       # sqlite | mysql | postgresql:方言差异(占位符、自增、JSON 列)由实现吸收
```

| 实现 | 备注 |
|---|---|
| **SQLite** | 单文件,零依赖;单机想要查询能力时的第一选择 |
| **MySQL / PostgreSQL** | 多机共用一个实例、多写者时用;连接串从环境变量来(行为不来自文件,同 `*muxd` 的规矩) |

方言差异(`?` vs `%s`、自增列、JSON 类型、`RETURNING`)由各实现吸收;仓储层写的 SQL 尽量只用交集,真绕不开的地方按 `dialect` 分支。

---

## 4. 仓储层:业务概念住在这里,按族各写一份

work / user 的记录(work 节点、画布、会话登记、谁动过、事件、收件箱、round、user 资料)是**业务**。业务层需要的操作定成一个接口——它长什么样是业务层的事,provider 不管;然后**按族各实现一份**:

| | fs 版仓储(用 `FileSystemProvider`) | db 版仓储(用 `DatabaseProvider`) |
|---|---|---|
| work 节点 | `works/<id>/work.json`,`read` / `write` | `works` 表,一行 |
| 画布 | `works/<id>/canvas.json`,版本号在文件里 | `canvases` 表,版本列 |
| 会话登记 / 谁动过 / manager | 各一个 JSON | 各一张表 |
| 事件 / 收件箱 / round | JSONL,`append` / `read` | `events` / `inbox` / `rounds` 表,自增 `seq` |
| 「按父列子」「按 created_by 列」 | `list` 前缀 + 读每个 `work.json` 在内存里过滤 | `WHERE parent = ?` / `WHERE created_by = ?`,走索引 |
| 把路径交给外部进程(agent 读 rounds) | `local_path`(LocalFS 有;S3 没有 → 退回 `read`) | 没有路径;把手改成通过仓储读 |

两点要说清:

- **业务接口一份,实现两份**——不是一份实现套两种 provider。因为两族的「自然写法」不同:文件系统就该整文件读写,数据库就该 SQL 查询;硬用一份代码适配两族,就是在其中一族上写别扭的代码。
- **同一族之内不用再分**:fs 版仓储对 LocalFS 和 S3 一视同仁(只在 `local_path` 上问一句);db 版仓储对 SQLite 和 MySQL 一视同仁(方言在 provider 里吸收)。

---

## 5. 选哪个:配置定,业务层不感知

```
MEMORY_TALK_STORE=fs            (默认)  → LocalFS,根在 MEMORY_TALK_HOME
MEMORY_TALK_STORE=s3   + bucket / 凭证  → S3
MEMORY_TALK_STORE=sqlite + 文件路径     → SQLite
MEMORY_TALK_STORE=mysql  + DSN          → MySQL
```

启动时按配置装配:选族 → 选实现 → 建对应的仓储 → 交给业务层。业务层拿到的是仓储接口,不知道底下是文件还是表。

**混搭**:某些流可以指定另一个 provider——典型是 rounds:主存储用 MySQL,rounds 仍用 LocalFS(大、只增、要给 agent 一个路径)。这是装配时的事,仓储层收到两个 provider,业务层仍只看到一份接口。

---

## 6. 和 collections 的边界

collections 的介质就是 git([collections-store.md](collections-store.md)),**不走 provider**。git 需要本机文件系统,这是硬要求。

但 provider 在 collections 那边有一个天然的位置:**blob 外置**。collectbase 把二进制放到 `blob/` 目录、原地留软链;那个 `blob/` 正是一个 `FileSystemProvider` 该管的东西——本地时是 LocalFS,想把大文件放远端时换 S3,collections 仓库里的软链不变。这是将来做 blob 外置时顺手的事,本篇记一笔。

---

## 7. 这篇有意不定的事

- **对象存储的 `append` 怎么做**:读回拼接(简单,小文件够用)还是一行一对象(可扩展,list 成本高)。先按前者;rounds 这种大流本来就建议留 LocalFS。
- **`watch` 要不要进基类**:前端实时性会要;LocalFS 用 inotify,S3 没有,数据库看实现。先作为能力,不进必须项。
- **db 版仓储的表结构**:一张宽表 `documents(kind, id, parent, created_by, version, data JSON)` 省事,每类一张表查询好;倾向每类一张表——既然选了数据库就把它的长处用上。
- **多写者**:LocalFS 假设单写者(进程内锁);数据库天然多写者。换到数据库后业务层要不要放开并发——放开就得处理 work 树上的竞争,先不。
- **迁移**:两份仓储都实现 `dump()` / `load()`,介质之间搬家就是导出再导入。格式定成什么(JSONL 一行一记录?)等要搬的时候再定。
