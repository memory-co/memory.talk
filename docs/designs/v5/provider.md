# provider —— user 和 work 的存储介质可换,上层不动(v5 设计)

> **状态:框架稿,未实施。** 本篇立存储 provider 这层抽象:**user 和 work 这两类记录**(裸文件那一半)不绑定特定介质——本地 JSON 可以,MySQL 也可以;介质以 provider 的形式提供,上层用的东西不变。但**文件系统 provider 和数据库 provider 的接口不会完全一样**,所以上层要在少数几处显式感知——本篇把「一样的部分」和「不一样的部分」划清。总定位见 [README.md](README.md)。

相关:
- v5 store(认知层进 git、现场层用裸文件——本篇只动「裸文件」那一半的介质): [collections-store.md](collections-store.md)
- v5 user / work(被存的两类记录): [user.md](user.md) / [work.md](work.md)
- v5 collections(**不在本篇范围**:它的介质就是 git): [collections.md](collections.md)

---

## 1. 一句话:两类记录、两个小接口、介质由 provider 给

memory.talk 落盘的东西分两半([collections-store.md §1](collections-store.md)):

| 半 | 是什么 | 介质 |
|---|---|---|
| collections | 认知层:分层 git 仓库 | **就是 git**,不换。它的价值(历史、因果、层)全在 git 上,换介质等于换掉它本身 |
| **works + users** | 现场层的记录:work 节点、画布、会话登记、谁动过、事件、收件箱、round;以及 user 的资料 | **本篇**:今天是 `~/.memory.talk/works/` 下的 JSON / JSONL;将来可以是 MySQL / PostgreSQL / SQLite——**由 provider 提供** |

上层(WorkService、user 那套、manager 的投递)**不直接 open 文件、不直接写 SQL**,只对着两个小接口说话:

```
Documents   一份份小记录:work.json / canvas.json / sessions.json / users.json / manager.json / 用户资料
            get / put(带版本) / delete / list(按父、按 created_by、按类型)
Logs        只追加的流:events.jsonl / inbox.jsonl / rounds.jsonl
            append / read(从某个位置起)
```

就这两个。它们是**从上层今天真正在用的操作里抽出来的**,不是一个通用 KV 或 ORM——接口越小,两种介质越容易都满足。

---

## 2. 为什么现在就要这层

- **单机单团队用 JSON 够了,但不是永远够。** 团队大了、多台机器共用一个实例、要按 user 查「我的 work」跨几千个目录——扫文件系统就慢了,这时要数据库。
- **上层不该为此改一遍。** work 树、user 名单、收件箱投递这些逻辑和介质无关;今天写死 `open()`,明天换库就是全改。现在就把介质隔开,代价很小(两个 Protocol)。
- **但也不能假装两种介质一样。** 文件系统能给出**路径**——agent 的把手读 `rounds.jsonl`、ttyd 的 attach 脚本看登记文件、人 `cat` 一下;数据库给不了路径,但能给**查询**——按 user、按状态、按时间过滤,文件系统只能扫。这两样差异是本质的,藏起来只会让上层在错的地方假设。

---

## 3. 一样的部分:核心接口

两种 provider **都必须实现**。上层的绝大多数代码只碰这里。

```python
class Documents(Protocol):
    def get(self, kind: str, id: str) -> Doc | None            # Doc = {id, kind, parent, created_by, version, data}
    def put(self, kind: str, id: str, data: dict, *, expect_version: int | None = None) -> Doc
    def delete(self, kind: str, id: str) -> None
    def list(self, kind: str, *, parent: str | None = None, created_by: str | None = None) -> list[Doc]

class Logs(Protocol):
    def append(self, stream: str, id: str, line: dict) -> None     # stream = events | inbox | rounds
    def read(self, stream: str, id: str, since: int = 0) -> list[dict]
```

要点:

- **`kind` 就是今天的文件名**:`work` / `canvas` / `sessions` / `users` / `manager` / `user`(资料)。`id` 是 work id(或 user 名)。文件系统 provider 把 `(kind, id)` 映射成 `works/<id>/<kind>.json`;数据库 provider 映射成一张表一行。
- **`put` 带版本**:画布已经在用乐观锁(`version`),把它提到接口上,两种介质都能给——文件系统用文件里的版本号,数据库用行版本列。
- **`list` 只按三样过滤**:`kind`、`parent`(work 树的父子)、`created_by`(user 的归属)。这是上层今天真正需要的全部;数据库能建索引,文件系统扫目录——**结果一样,快慢不同**,上层不用管。
- **原子性只到单份文档 / 单条追加**:文件系统就是这么保证的(原子写、追加),数据库也按行保证。**不承诺跨文档事务**——上层今天就没依赖它(work 结束时逐个销毁会话就是这么写的),将来也别依赖。

---

## 4. 不一样的部分:能力

两种 provider **不必都有**的东西,上层用之前要问一句。

| 能力 | 谁有 | 上层哪里用 | 没有时怎么办 |
|---|---|---|---|
| **`paths`**:一份文档 / 一条流对应的**本机路径** | 文件系统 | agent 把手直接读 `rounds.jsonl`;attach 脚本校验登记;人 `cat` | 数据库 provider 没有。上层改走 `Logs.read`(把手已经是通过接口读的,只有「给外部进程一个路径」的地方需要它);真要路径,provider 可以**spool**——把那条流导出到临时文件,用完丢 |
| **`query`**:任意条件过滤 / 排序 / 分页 | 数据库 | 「按 user 看最近 30 天的 work」「全团队正在动的 work」这类视图 | 文件系统 provider 没有。上层退回 `list` + 内存过滤;数据量小时够用,大了就是换库的信号 |
| **`watch`**:某条流有新行时通知 | 文件系统(inotify)可有;数据库看实现 | 前端实时看收件箱、rounds 流出来 | 都没有就轮询 |

上层这样感知:

```python
store = load_provider(config)           # fs | mysql | …
if store.has("paths"):
    handle = server.open(..., rounds_path=store.paths.log("rounds", session_id))
else:
    handle = server.open(..., rounds=lambda: store.logs.read("rounds", session_id))
```

**只在这几处感知,别处一律只用核心接口。** 能力是显式的、可探的、有降级的——这比把两种介质硬压成一个接口、然后在文件系统上假装能查询(慢到不可用)或在数据库上假装有路径(根本没有)诚实得多。

---

## 5. 两个 provider 长什么样

| | fs(默认) | mysql(将来;PostgreSQL / SQLite 同理) |
|---|---|---|
| Documents | `works/<id>/<kind>.json`,原子写(临时文件 + rename),`version` 存在文件里;`user` 资料在 `users/<名>.json` | 一张 `documents(kind, id, parent, created_by, version, data JSON)` 表,或每 kind 一张表——由 provider 定,上层不感知 |
| Logs | `works/<id>/{events,inbox}.jsonl`、`works/<id>/sessions/<sid>/rounds.jsonl`,append | `logs(stream, id, seq, line JSON)`,`seq` 自增 |
| 能力 | `paths`、可选 `watch` | `query`、可选 `watch` |
| 配置 | 无(默认) | `MEMORY_TALK_STORE=mysql` + DSN——**行为不来自文件**,同 `*muxd` 的规矩 |
| 迁移 | 两边都实现 `dump()` / `load()`(走核心接口),介质之间搬家就是导出再导入 | 同 |

**rounds 特殊**:它大、增长快、每轮都记。即使用了数据库,rounds 也可以**留在文件系统**——provider 允许**按流混搭**(`rounds` 用 fs,其余用 mysql)。这是 [origin.md §6](origin.md) 说的「痕迹和材料分开放」在介质上的体现:过程留在本机,记录进库。混搭是 provider 的配置,上层看到的还是 `Logs`。

---

## 6. 和 collections 的边界

collections **不走 provider**。理由已经在 [collections-store.md §2](collections-store.md):它要的是历史、因果、层——那是 git 本身,不是「一种介质上的记录」。真要把认知层放到别处,答案是 git remote(push / pull),不是换成表。

两边的引用照旧是裸 id:collections 里的 `Work:` trailer、issue 的 `work_id`,指向 works 那半;works 的收件箱条目指向 collections 的路径。介质换了,id 不变,引用不变。

---

## 7. 这篇有意不定的事

- **user 资料要不要现在就落成 Documents 的一个 kind**:[user.md §7](user.md) 说 user 现在只是名字,没有清单。倾向先把 `kind="user"` 留在接口里,fs provider 下 `users/<名>.json` 可以为空目录——接口有、内容等需求。
- **rounds 的 `since`**:文件系统按行号,数据库按 `seq`。要不要统一成「provider 给一个不透明的 cursor」——倾向是,`since` 就是 cursor,上层原样带回。
- **`watch` 要不要进核心接口**:前端实时性会要;但两种介质实现难度差很多。先放能力。
- **多进程 / 多实例写同一个 provider**:文件系统 provider 假设单写者;数据库天然多写者。上层今天按单写者写的(进程内锁),换库后要不要放开——放开就得处理并发,先不。
- **provider 的粒度**:一个 provider 管全部 kind + stream,还是可以每个 kind 指定(§5 的混搭)。倾向:一个主 provider + 少数流可覆盖(`rounds`),别做成每 kind 一个。
