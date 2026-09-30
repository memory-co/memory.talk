# work-store —— work 的记录存在哪:local 或 db(v5 设计)

> **状态:已实施。** 本篇把 work 这一半的存储讲清楚:一个 work 有哪几样记录,各是什么形状,在 **local**(`MEMORY_TALK_STORE=fs`,本地文件系统)和 **db**(`MEMORY_TALK_STORE=sqlite`)两种形态下分别落在哪里。重点回答两个问题:**列布局(画布)存在哪**、**事件存在哪**。provider 这层抽象本身见 [provider.md](provider.md)。本篇只讲 work 的仓储怎么用它。

相关:
- provider 两族基类(文件系统型 / 数据库型),仓储按族各写一份: [provider.md](provider.md)
- 画布是显示层,快照和事件各存各的: [work.md](work.md) / [work-events.md](work-events.md)
- worklet 的身份脱离布局(登记和画布分开存): [worklet.md](worklet.md)
- 认知层在 git 里,不在本篇: [metas/store.md](metas/store.md)
- 目录 / 表的速查: [`../../structure/v5/filesystem.md`](../../structure/v5/filesystem.md)
- 代码:`memorytalk/backend/services/work/repo.py`(`FsWorkRepo` / `DbWorkRepo`)

---

## 1. 一句话:三种形状,一份接口,两种落法

work 的记录不管存在哪,都只有三种形状:

| 形状 | 是什么 | 怎么写 |
|---|---|---|
| **节点** | work 本身:目标、父、状态、谁建的 | 整份替换 |
| **小记录(doc)** | 挂在一个 work 下的一份 JSON,按 `kind` 区分:`canvas`、`worklets`、`seq`、`users`、`manager` | 整份替换 |
| **流(stream)** | 挂在一个 work 下的只追加序列,按名字区分:`events`、`inbox`、`rounds`(再按 worklet 分) | 只追加,从不改旧行 |

业务层只认一个接口 `WorkRepo`:`get_work / put_work / list_works`、`get_doc / put_doc / del_doc`、`append / read`、`append_unmanaged`。**画布、登记、事件这些概念只出现在业务层**(`canvas.py`、`worklets.py`、`events.py`……),仓储只知道「某个 work 的某个 kind」「某个 work 的某条流」。启动时 `StoreService` 按 `MEMORY_TALK_STORE` 选 provider,`make_work_repo` 按族给出 `FsWorkRepo` 或 `DbWorkRepo`,业务层不知道底下是什么。

## 2. 一个 work 有哪些记录

| 记录 | 形状 | kind / 流名 | 谁写 | 说明 |
|---|---|---|---|---|
| work 节点 | 节点 | — | `tree.py` | `id / goal / parent / status / created_by / created_at …` |
| **画布(列布局)** | doc | `canvas` | `canvas.py` | 几列、每列装哪些工作单元、收起没有;见 §5 |
| 工作单元登记 | doc | `worklets` | `worklets.py` | 数组:`id / uri / scheme / server / cwd / created_at / last_attached`。**不含位置** |
| 计数器 | doc | `seq` | `worklets.py` | `{"worklet": n}`:下一个工作单元编号,单调递增、不复用 |
| 谁动过 | doc | `users` | `users.py` | 只做可见性 |
| manager | doc | `manager` | `WorkService` | `{"work": <id>}`;没有 = 用父 work 的 |
| **事件(时间线)** | 流 | `events` | `events.py` | 见 §6 |
| 收件箱 | 流 | `inbox` | `inbox.py` | manager 路由过来的变动 |
| round | 流(按 worklet 分) | `rounds` + `sub=<worklet_id>` | `rounds.py` | agent 工作单元的痕迹 |
| 没人管的变动 | 流(全局) | `unmanaged` | `inbox.py` | 不属于任何 work |

画布和工作单元登记是**两份**:登记回答「有哪些现场」,画布回答「它们摆在哪」。画布里的格子只存 worklet id,关掉工作单元时两边各删各的([worklet.md](worklet.md))。

## 3. local:目录就是树

`MEMORY_TALK_STORE=fs`(默认),provider 是 `LocalFS`,根在 `MEMORY_TALK_HOME`(默认 `~/.memory.talk`)。

```
<home>/
├── works/
│   └── <work_id>/                        ← 根 work
│       ├── work.json                     ← 节点
│       ├── canvas.json                   ← doc:画布(列布局)
│       ├── worklets.json                 ← doc:工作单元登记
│       ├── seq.json                      ← doc:编号计数器
│       ├── users.json                    ← doc:谁动过
│       ├── manager.json                  ← doc(可选)
│       ├── events.jsonl                  ← 流:时间线
│       ├── inbox.jsonl                   ← 流:收件箱
│       ├── worklets/<worklet_id>/rounds.jsonl   ← 流:round,按 worklet 分
│       └── subs/<child_id>/              ← 子 work,结构和父一样,可以一直往下套
└── unmanaged.jsonl                       ← 全局流
```

规则:

- **路径规则**:doc 是 `<work 目录>/<kind>.json`,流是 `<work 目录>/<流名>.jsonl`,带 `sub` 的流在 `<work 目录>/worklets/<sub>/<流名>.jsonl`。
- **目录就是树**:子 work 住在父目录的 `subs/` 下,建的时候按 `parent` 定位置,之后不搬。`works/` 这一层只有根 work。
- **id → 目录**:仓储启动后懒扫一遍 `works/**/work.json` 建内存索引,建 work 时顺手登记;找不到就重扫。`list_works` 每次都重扫、读每个 `work.json` 再过滤,量级是「一个团队的 work 数」,够用。
- **doc 原子写**:写临时文件 `.tmp-*` 再 `os.replace`,读的人要么看到旧的一整份,要么看到新的一整份。
- **流只追加**:`open(..., "ab")` 写一行 JSON + `\n`。读就是整个文件按行解析。
- **人能直接看**:`cat canvas.json`、`tail -f events.jsonl`、`grep` 都行。这是 local 形态最大的好处。

## 4. db:三张表

`MEMORY_TALK_STORE=sqlite`,provider 是 `SQLite`,文件默认 `<home>/memory.sqlite`(`MEMORY_TALK_SQLITE` 可改),WAL 模式,进程内一把锁串行化。仓储不写 SQL,用 provider 的 `table / select / insert / update / delete` 原语。work 这一半一共三张表:

| 表 | 列 | 装什么 |
|---|---|---|
| `works` | `id`(主键)、`parent`(索引)、`created_by`(索引)、`status`、`data`(JSON) | 节点。整个 work 放在 `data` 里,另外把**要查的字段提出来当列**:按父列子 work、按建的人筛,走索引 |
| `work_docs` | `pk`(主键,`<work_id>/<kind>`)、`work_id`(索引)、`kind`、`data`(JSON) | 所有 doc。一个 work 的一个 kind 一行;`put_doc` = 先 update,没更新到就 insert |
| `work_logs` | `seq`(自增主键)、`key`(索引)、`line`(JSON) | 所有流,混在一张表里,用 `key` 区分:`<work_id>/<流名>`,带 sub 的 `<work_id>/<流名>/<sub>`,全局的 `unmanaged`。读 = 按 `key` 筛、按 `seq` 升序 |

(同一个 sqlite 文件里还有 `users`、`auth_tokens` 两张表,不属于 work。)

和 local 的对应关系是一一的:`work.json` ↔ `works` 一行;`<kind>.json` ↔ `work_docs` 一行;`<流>.jsonl` 的每一行 ↔ `work_logs` 的一行。**树在 db 里不靠目录,靠 `parent` 列**:子 work 就是 `parent = 父 id` 的行,没有 `subs/` 这层。

## 5. 列布局存在哪

**存在 `canvas` 这份 doc 里**:local 是 `works/<…>/<work_id>/canvas.json`,db 是 `work_docs` 里 `pk = "<work_id>/canvas"` 那一行的 `data`。内容就是 `Canvas` 模型:

```json
{
  "version": 12,
  "next_column": 4,
  "columns": [
    {"id": "c1", "alias": "",     "collapsed": false,
     "panels": [{"worklet": "work_…-w1", "collapsed": false},
                {"worklet": "work_…-w3", "collapsed": true}]},
    {"id": "c3", "alias": "测试", "collapsed": false,
     "panels": [{"worklet": "work_…-w4", "collapsed": false}]}
  ]
}
```

| 字段 | 说明 |
|---|---|
| `columns` | 从左到右。**顺序就是列表顺序**,没有单独的位置字段 |
| `columns[].id` | `c<编号>`,服务端发,永不改、不复用([work-events.md §3](work-events.md)) |
| `columns[].alias` | 别名,可空。旧数据里叫 `name`,读的时候当 `alias` |
| `columns[].panels` | 从上到下,每格只存 `worklet`(id)和 `collapsed` |
| `columns[].collapsed` | 整列收起 |
| `next_column` | 下一列的编号;删了列号也不还 |
| `version` | 每次动作 +1,前端拿来判断缓存旧没旧 |

几条规则:

- **整份存、整份取**:画布是一个 doc,不拆成「列表」「格子表」。它小(几列、十几格),一次动作读-改-写一整份最简单,两种形态写法一样。
- **只有 `CanvasStore` 写它**:每个动作(加列、改别名、删列、放 / 挪 / 拿掉工作单元、收起)一个方法,在进程内一把锁下读当前画布、改、`version + 1`、存回。没有 `PUT` 整份覆盖。
- **读时规整,不回写**:没有画布(新 work)读出来补一列 `c1`;早期不是 `c<n>` 的列 id 接着发号;`next_column` 至少是最大编号 + 1。规整只在内存里做,下一次动作存回时才落盘。
- **它是快照,不是真相来源**:画布是显示层,丢了、乱了都不伤 work。它**不从事件重放出来**,事件也不从它 diff 出来([work-events.md §5](work-events.md))。

## 6. 事件存在哪

**存在 `events` 这条流里**:local 是 `works/<…>/<work_id>/events.jsonl`,一行一条;db 是 `work_logs` 里 `key = "<work_id>/events"` 的那些行,按 `seq` 排。每条就是 `Event` 模型:

```json
{"ts": "2026-09-29T10:02:11Z", "type": "worklet.attached",
 "data": {"by": "alice", "worklet": "work_…-w4", "uri": "bash:///ws", "server": "bash",
          "column": {"id": "c3", "alias": "测试"}}}
```

- **只追加**:从不改、不删旧行。事件的顺序在 local 是文件里的行序,在 db 是 `seq`。两者都是写入顺序;`ts` 只给人看,不拿来排。
- **一个 work 一条流**:子 work 的事件在子 work 自己那里(local 在 `subs/<child>/events.jsonl`,db 是 `key = "<child_id>/events"`),父 work 不汇总。
- **类型和字段**见 [work-events.md](work-events.md) 的动作表和 [`../../structure/v5/work.md`](../../structure/v5/work.md#event):`created / status / frozen`、`column.added / renamed / removed`、`worklet.attached / moved / detached`,每条带 `by`,和列有关的带 `column: {id, alias}` 快照。
- **谁读它**:时间线接口(`GET /works/{id}/events`);另外 `worklets.py` 给没有 `seq` 的旧 work 发编号时,会扫一遍事件里出现过的 `-w<n>`,保证关掉的号不再用。
- **收件箱、round 同理**:`inbox.jsonl` / `key = "<work_id>/inbox"`;`worklets/<wid>/rounds.jsonl` / `key = "<work_id>/rounds/<wid>"`;没人管的变动在根上的 `unmanaged.jsonl` / `key = "unmanaged"`。

## 7. 一个动作写了哪几处

以「在 列 3 打开一个终端」为例(`WorkService.attach`),依次:

1. `worklets` doc:登记里加一条(同时 `seq` doc 的计数 +1)
2. (tmuxd 建现场;建不起来就把第 1 步的登记删掉,到此为止)
3. `canvas` doc:`c3` 的 `panels` 末尾加一格,`version + 1`
4. `events` 流:追加 `worklet.attached`

**两种形态都没有跨记录的事务**:每一步是一次独立的整份替换或追加。顺序是有意的:先登记、再摆、最后记事件。中途出错的后果按严重程度往后排:登记在、画布没摆上,现场还在,重开页面能看到;画布摆上了、事件没写上,时间线少一条,不影响干活([work-events.md §5](work-events.md))。服务是这些记录的唯一写者,进程内的锁保证同一种记录的读-改-写不交错。

## 8. 两种形态怎么选

| | local(`fs`) | db(`sqlite`) |
|---|---|---|
| 默认 | 是 | 否 |
| 人直接看 | `cat` / `grep` / `tail -f`,目录就是树 | 要开 sqlite |
| 按父 / 建的人列 work | 扫目录、读每个 `work.json` 再过滤 | 走 `parent` / `created_by` 索引 |
| 读一条流 | 读整个文件 | 按 `key` 索引筛 |
| 备份 | 拷目录 | 拷一个文件(WAL 下先 checkpoint) |
| 写者 | 单进程 | 单进程(进程内锁;多进程写不在 v5 范围) |

两者在接口上完全等价,测试套件对每个用到存储的场景都 **fs 和 sqlite 各跑一遍**。选哪个只看运维习惯:想直接翻文件用 local,work 多了想要索引用 db。

**切换不带数据**:改 `MEMORY_TALK_STORE` 之后,新介质里是空的;没有迁移工具。要迁的话按 §4 的一一对应关系逐条搬(节点 → `works`,doc → `work_docs`,每行流 → `work_logs`,流内顺序保持)。

## 9. 这篇有意不定的事

- **跨记录事务**:§7 的几步要不要在 db 形态下包成一个事务。local 形态做不到,两边行为会不一致;现在按「顺序写、后果可接受」统一处理。
- **流分表**:所有流挤在 `work_logs` 一张表里,round 量大了会拖慢事件和收件箱的读。到时候再按流名拆表,或者按 [provider.md §5](provider.md) 的混搭,把 round 单独放到 local。
- **MySQL / PostgreSQL / OSS / S3**:provider.md 里列了,还没实现。仓储按族写,接上以后 work 这一半不用改。
- **迁移工具**:local ↔ db 之间搬数据,等真有人要换的时候再写。
