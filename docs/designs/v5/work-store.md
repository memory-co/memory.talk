# work-store —— work 存在两个 sqlite 里:works.db 管现在,worktrace.db 管经过(v5 设计)

> **状态:设计中,未实施(改版)。** 上一版是两种形态可选:local 把 work 的记录散成目录树里的文件,db 用一个 sqlite。这一版**只留 sqlite**,并且拆成两个文件:
>
> - **`works.db`**:work 的全部信息,也就是它**现在**是什么样;
> - **`worktrace.db`**:work 的全部轨迹,也就是它**怎么走到现在**的。
>
> work 这一半不再有文件系统那套,仓储只剩一份实现,用的是同一种 provider(`SQLite`)。本篇讲清楚每样记录在哪个库、哪张表,重点是**列布局存在哪**、**轨迹(原来的 events)存在哪**。

相关:
- provider 的两族基类: [provider.md](provider.md)。work 这一半以后只用数据库型
- 轨迹的模型(段 / 点、OTel 字段): [work-trace.md](work-trace.md)
- 画布是显示层;快照和轨迹各存各的: [work.md](work.md) / [work-events.md](work-events.md)
- worklet 的身份脱离布局(登记和画布分开存): [worklet.md](worklet.md)
- 认知层在 git 里,不在本篇: [metas/store.md](metas/store.md)

---

## 1. 为什么改:一套 provider,两个库

**不要文件那套了。** 上一版为了两种形态,仓储写了两份(`FsWorkRepo` / `DbWorkRepo`),测试也按 fs、sqlite 各跑一遍;为了让两边长得一样,db 那边只能迁就文件的形状:一张 `work_docs` 装所有 JSON doc,一张 `work_logs` 装所有流。只留 sqlite 以后:

- **仓储只有一份**,表可以按业务来设计。登记是一行一个工作单元,不再是一整个数组塞进一个 doc;要查的字段都是真的列。
- **一个动作可以是一个事务**。「在列 3 打开终端」要改登记、计数器、画布三处,以前是三次独立的写,现在在 `works.db` 里一次提交(§6)。
- **没有目录扫描**。按父列子 work、按建的人筛,都走索引。

**为什么是两个库,不是一个:** 现在的状态和经过的轨迹,性质完全不一样。

| | `works.db`(现在) | `worktrace.db`(经过) |
|---|---|---|
| 装什么 | work 节点、画布、登记、谁动过、manager、收件箱 | 段、点(work-trace.md)、agent 的 round |
| 读写 | 读多写少,每次动作读-改-写几行 | 几乎只追加,量随时间一直涨 |
| 体量 | 小,和 work 数、工作单元数成正比 | 大,和发生过多少事成正比;round 尤其大 |
| 丢了会怎样 | 丢了就丢了 work | 丢了只是少了历史,work 照样能干活 |
| 运维 | 要好好备份 | 可以归档、截断、单独拷给可观测那边分析 |

分成两个文件,两边各有自己的 WAL 和写锁,轨迹写得再多也不会挡住状态的读写;备份、归档、清理也能分开做。这和 work-events.md §5 定下的原则是一致的:**快照管「现在」,轨迹管「经过」**。

## 2. 在哪、怎么配

```
<MEMORY_TALK_HOME>/
├── works.db          ← 现在(+ works.db-wal / works.db-shm)
└── worktrace.db      ← 经过(+ worktrace.db-wal / worktrace.db-shm)
```

- 默认都在 `MEMORY_TALK_HOME` 下;`MEMORY_TALK_WORKS_DB` / `MEMORY_TALK_WORKTRACE_DB` 可以分别改路径,比如把轨迹放到更大的盘上。
- 每个库一个 `SQLite` provider 实例,各自开 WAL,各自一把进程内锁。仓储构造时拿到两个 provider:`WorkRepo(works: DatabaseProvider, trace: DatabaseProvider)`。
- `MEMORY_TALK_STORE` 不再决定 work 存在哪。users / auth 放在哪,见 §8。
- 表结构启动时按仓储里的声明建(`provider.table(...)` / `ensure_table`),不手写迁移 SQL。

## 3. works.db:work 的全部信息

| 表 | 主键 | 列 | 说明 |
|---|---|---|---|
| `works` | `id` | `parent`(索引)、`goal`、`status`、`created_by`(索引)、`created_at`、`archived_at`、`manager`、`next_worklet` | work 节点。`manager` 是这棵子树的变动打给谁(空 = 用父 work 的);`next_worklet` 是下一个工作单元的编号,单调递增、不复用(原来的 `seq` doc)。**树就是 `parent` 列** |
| `canvases` | `work_id` | `version`、`next_column`、`columns`(JSON) | 画布,一个 work 一行。见 §4 |
| `worklets` | `id` | `work_id`(索引)、`uri`、`scheme`、`server`、`cwd`、`created_at`、`last_attached` | 工作单元登记,一个一行。**不含位置**,位置在画布里 |
| `work_users` | (`work_id`, `user`) | `first_seen`、`last_seen`、`ops` | 谁动过,只做可见性 |
| `inbox` | `seq`(自增) | `work_id`(索引,空 = 没人管)、`ts`、`item`(JSON) | 收件箱:manager 路由过来的变动。原来的 `unmanaged.jsonl` 就是 `work_id` 为空的那些行 |

收件箱放在 `works.db` 而不是 `worktrace.db`:它是别的地方打给这个 work 的消息,等着被处理,属于这个 work 的「现在」;轨迹记的是这个 work 自己做过什么。

## 4. 列布局存在哪

**存在 `works.db` 的 `canvases` 表里,一个 work 一行。** 布局本身放在 `columns` 这一列,是一个 JSON 数组;`version` 和 `next_column` 是单独的列:

```
canvases
  work_id      = "work_202609291002…"
  version      = 12
  next_column  = 4
  columns      = [
    {"id": "c1", "alias": "",     "collapsed": false,
     "panels": [{"worklet": "work_…-w1", "collapsed": false},
                {"worklet": "work_…-w3", "collapsed": true}]},
    {"id": "c3", "alias": "测试", "collapsed": false,
     "panels": [{"worklet": "work_…-w4", "collapsed": false}]}
  ]
```

| 字段 | 说明 |
|---|---|
| `columns` | 从左到右,**数组顺序就是列的顺序**;每列 `id`(`c<编号>`,永不改、不复用)、`alias`、`collapsed`、`panels` |
| `columns[].panels` | 从上到下,每格只存 `worklet`(id)和 `collapsed` |
| `next_column` | 下一列的编号;删了列号也不还 |
| `version` | 每个动作 +1,前端拿来判断缓存旧没旧 |

**为什么列不拆成表:** 布局很小(几列、十几格),每个动作都是读一整份、改、写回一整份;列的顺序、格子的顺序都是数组下标,拆成 `columns` / `panels` 两张表就得维护排序字段,换来的只是没人用的 SQL 可查性。所以版本号和计数器是列,形状本身是 JSON。

规则沿用上一版:只有 `CanvasStore` 写它;每个动作在一个事务里读-改-写,`version + 1`;新 work 没有这一行时,读出来补一列 `c1`;画布是快照,不从轨迹重放出来,也不从它 diff 出轨迹。

## 5. worktrace.db:work 的全部轨迹

**原来的 `events` 流整个搬到这里,换成 work-trace.md 的「段 + 点」。** 字段按 OTel 的 span / log record **一对一**存:id 是十六进制字符串,时间是 Unix 纳秒整数,属性是 OTLP 的 `KeyValue` 列表(JSON)。所以任何一行都能无损拼回一个 OTLP/JSON 的 span 或 log record。落盘是按列存的,方便按 work、按时间查;对外(`GET /works/{id}/trace`、OTLP 导出)时再拼成标准的信封。

| 表 | 主键 | 列 | 说明 |
|---|---|---|---|
| `spans` | `span_id` | `trace_id`(索引)、`parent_span_id`、`work_id`(索引)、`name`、`kind`、`start_time_unix_nano`、`end_time_unix_nano`、`status_code`、`attributes`(JSON)、`links`(JSON) | 段:`work` / `worklet` / `agent.turn`。**`end_time_unix_nano` 为空 = 还开着**。结束 = 在同一行填上终点和结束时的属性 |
| `points` | `seq`(自增) | `trace_id`、`span_id`(索引)、`work_id`(索引)、`event_name`、`time_unix_nano`、`attributes`(JSON) | 点:`column.*`、`worklet.moved`、`plan.changed`……只追加 |
| `rounds` | `seq`(自增) | `work_id`、`worklet_id`(索引)、`round_id`、`timestamp`、`role`、`text` | agent 工作单元的 round(原来的 `rounds.jsonl`)。`agent.turn` 段通过 round id 引用它 |

几条规则:

- **开着的段就是一行没有终点的记录。** work-trace.md §3 为这个问题另外开了一份 `spans` doc(因为 jsonl 只能追加一整条);到了表里,「开着」只是一列为空,不用再单独存一份状态。**只追加的是 `points` 和 `rounds`;`spans` 每行最多改一次**,就是结束那次。
- **一个 work 的轨迹** = `work_id = ?` 的段和点;**一棵树的轨迹** = 同一个 `trace_id`(work-trace.md §4)。两个都有索引。
- **round 放在这里**,是因为它和段、点的性质一样:只追加、量大、是「经过」。放进 `works.db` 会让状态库越长越大,备份也越来越慢。
- 对外导出只发**已经结束**的段(OTLP 没有「开着的 span」),点随写随发。怎么导出见 work-trace.md §8。

## 6. 一个动作写了哪几处

以「在 列 3 打开一个终端」为例:

1. 先验列在不在(读 `canvases`);不在直接 404,不建现场
2. **建现场**(tmuxd);建不起来到此为止,什么都没写
3. **`works.db` 一个事务**:`works.next_worklet + 1`,`worklets` 插一行,`canvases` 里 `c3` 的 `panels` 末尾加一格、`version + 1`
4. **`worktrace.db`**:`spans` 插一行 `worklet` 段(开着,父是这个 work 的 work 段)

两步写要注意:

- **两个库之间没有原子提交。** 两个库都是 WAL 模式,sqlite 在 WAL 下即使 `ATTACH` 在一起,跨库事务也只保证每个库各自原子,不保证两个库一起提交。所以顺序固定为**先 `works.db`,后 `worktrace.db`**。后一步失败的话,轨迹少一段,work 本身没问题。这和「轨迹丢了不伤 work」是同一个取舍。
- **现场和登记之间也不是原子的。** 把建现场挪到写库之前,是为了失败时什么都不用回滚(上一版是先登记、建失败再删)。反过来,现场建起来了但库写失败,就会留下一个没有登记的 tmux 会话;这种会话启动时对一遍就能收掉,和 work-trace.md §5「现场没了的段」是同一个对账过程,方向相反。

## 7. 从上一版怎么过来

**不做兼容。** 上一版的 `works/` 目录树、`memory.sqlite` 里的 `works` / `work_docs` / `work_logs` 三张表,实施时都不再读。现有实例的 work 数据不迁移,重新开始(和切换到 tmuxd 3.0 时对待 8090 实例的做法一样)。

要删掉的东西:`FsWorkRepo`、`DbWorkRepo` 里 doc / log 的通用写法、`MEMORY_TALK_STORE` 对 work 的作用、测试里 work 场景按 fs / sqlite 双跑的那一半参数。同时要改的文档:provider.md(work 不再用文件系统族)、`structure/v5/filesystem.md`(`works/` 目录没了,换成两个 db 文件)、`structure/v5/work.md`、work-trace.md §3(落盘改成 §5 的两张表)。

## 8. 这篇有意不定的事

- **users / auth 放哪。** 它们现在跟着 `MEMORY_TALK_STORE` 走(fs 下是 `users/`、`auth/tokens/`,sqlite 下在 `memory.sqlite` 里)。它们不属于 work。倾向:同样只留 sqlite,单独一个 `users.db`,或者并进 `works.db`。放进 `works.db` 能少一个文件,但 users 本来就不是 work 的信息。到时候单独定。
- **worktrace.db 怎么变老。** 轨迹会一直涨。可以按时间切(`worktrace-2026Q4.db`,查询时 `ATTACH`),也可以把已结束的 work 的轨迹导出成 OTLP/JSON 文件归档,再从库里删掉。先不做,等体量真大了再定。
- **round 要不要再单独一个库。** agent 的 round 是三张表里最大的。如果它把 `spans` / `points` 的查询拖慢了,再拆成 `worktrace.db` + `rounds.db`。表结构不用变,只是换个文件。
- **多进程。** 两个库都只由服务进程写。CLI 和 agent 都走 HTTP API,不直接开库。
