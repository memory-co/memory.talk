# work-store —— work 存在两个 sqlite 里:works.db 管现在,worktrace.db 管经过(v5 设计)

> **状态:已实施。** 仓储是 `services/work/repo.py` 的 `WorkRepo`(works.db)和 `TraceRepo`(worktrace.db),由 `StoreService` 各开一个 `SQLite` provider,`WorkService` / `MetasService`(投递收件箱)/ `UserService`(统计)共用这一份;provider 补上了组合主键和多列索引(§7)。上一版是两种形态可选:local 把 work 的记录散成目录树里的文件,db 用一个 sqlite。这一版**只留 sqlite**,并且拆成两个文件:
>
> - **`works.db`**:work 的全部信息,也就是它**现在**是什么样;
> - **`worktrace.db`**:work 的全部轨迹,也就是它**怎么走到现在**的。
>
> work 这一半不再有文件系统那套,仓储只剩一份实现,用的是同一种 provider(`SQLite`)。本篇讲清楚每样记录在哪个库、哪张表,重点是**列和工作单元的位置存在哪**、**轨迹(原来的 events)存在哪**。

相关:
- provider 的两族基类: [provider.md](provider.md)。work 这一半以后只用数据库型
- 轨迹的模型(段 / 点、OTel 字段): [work-trace.md](work-trace.md);agent 的记录由节点推进来: [work-node.md](work-node.md)
- 列只承载弱编排;现在和经过各存各的: [work.md](work.md) / [work-events.md](work-events.md)
- worklet 的身份不挂在位置上(挪到别的列还是它): [worklet.md](worklet.md)
- 认知层在 git 里,不在本篇: [metas/store.md](metas/store.md)

---

## 1. 为什么改:一套 provider,两个库

**不要文件那套了。** 上一版为了两种形态,仓储写了两份(`FsWorkRepo` / `DbWorkRepo`),测试也按 fs、sqlite 各跑一遍;为了让两边长得一样,db 那边只能迁就文件的形状:一张 `work_docs` 装所有 JSON doc,一张 `work_logs` 装所有流。只留 sqlite 以后:

- **仓储只有一份**,表可以按业务来设计。登记是一行一个工作单元(连同它摆在哪),每一列也是一行,不再把一整个数组塞进一个 JSON;要查的字段都是真的列。
- **一个动作可以是一个事务**。「在列 3 打开终端」要改计数器、登记、列里的位置三处,以前是三次独立的写,现在在 `works.db` 里一次提交(§6)。
- **没有目录扫描**。按父列子 work、按建的人筛,都走索引。

**为什么是两个库,不是一个:** 现在的状态和经过的轨迹,性质完全不一样。

| | `works.db`(现在) | `worktrace.db`(经过) |
|---|---|---|
| 装什么 | work 节点(含当前谁在看)、列、登记(连同每个工作单元在哪一列第几个)、manager、收件箱 | 段、点(work-trace.md;agent 的会话、轮次、工具调用和消息也在这里) |
| 读写 | 读多写少,每次动作读-改-写几行 | 几乎只追加,量随时间一直涨 |
| 体量 | 小,和 work 数、工作单元数成正比 | 大,和发生过多少事成正比;agent 的消息正文尤其大 |
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
- 每个库一个 `SQLite` provider 实例,各自开 WAL,各自一把进程内锁。一个库一个仓储:`WorkRepo(works.db 的 provider)`、`TraceRepo(worktrace.db 的 provider)`,由 `StoreService` 建好交给各个服务。`GET /api/system/info` 带上两个路径(`works_db` / `worktrace_db`),`memory.talk server status` 打出来。
- `MEMORY_TALK_STORE` 不再决定 work 存在哪。users / auth 放在哪,见 §8。
- 表结构启动时按仓储里的声明建(`provider.table(...)` / `ensure_table`),不手写迁移 SQL。

## 3. works.db 有哪些表

**原则:一张表一种东西,一行一个实体,要查、要单独改的都是真的列。** 这条不是「不许存 JSON」。它来自写代码时的实际感受:如果一份嵌套的 JSON 里装着好几个有身份、会被不同动作分别改动的东西(原来整份存成一个 JSON 的列和列里的工作单元就是这样),那么每个动作都得 load 整份、在内存里找到要改的那一处、改完再 dump 回去。读的地方要 load,查的地方要拍平,并发时还得靠一把锁防止互相覆盖,代码到处都是 load / dump,越写越乱。拆成行以后,每个动作就是改几行,查询就是 SQL。

所以列是 `work_columns` 的行,工作单元摆在哪是 `worklets` 自己的几列;收件箱的字段也是列。反过来,一个没有内部身份、只会整份写、平时也不按内容查的小东西,放在一个字段里就好,比如 `works.viewers` 这个数组。

```
works ──┬──< works          (parent:子 work)
        ├──< work_columns   (这个 work 的列)
        │        └──< worklets   (column_number + position:摆在哪一列第几个)
        └──< inbox          (收件箱;work_id 为空 = 没人管)
```

| 表 | 一行是 | 主键 | 其余列 |
|---|---|---|---|
| `works` | 一个 work | `id` | `parent`(索引)、`goal`、`status`、`created_by`(索引)、`created_at`、`archived_at`、`manager`、`viewers`、`next_worklet`、`next_column` |
| `work_columns` | 一列 | (`work_id`, `number`) | `alias`、`collapsed`、`position`;索引 (`work_id`, `position`) |
| `worklets` | 一个工作单元 | `id` | `work_id`(索引)、`number`、`uri`、`scheme`、`server`、`cwd`、`created_at`、`last_attached`,**加上位置**:`column_number`、`position`、`collapsed`;索引 (`work_id`, `column_number`, `position`) |
| `inbox` | 一条打过来的变动 | `seq`(自增) | `work_id`(索引,空 = 没人管)、`ts`、`layer`、`path`、`subject`、`sha`、`by`、`routed_by` |

各表说明:

- **`works`**:树就是 `parent` 列。`manager` 是这棵子树的变动打给谁(空 = 用父 work 的)。两个计数器:`next_worklet` 是下一个工作单元编号,`next_column` 是下一列编号,都单调递增、不复用。
- **`work_columns`**:一列一行,见 §4。
- **`worklets`**:一个工作单元一行,既是登记,也记着它摆在哪一列第几个。`number` 就是 id 里 `-w<n>` 的 n,单独存一列方便排序。位置那三列见 §4。
- **`works.viewers`:现在谁在看这个 work。** 一个字段,值是当前在看的人名(`["alice","bob"]`,按名字排);没人看就是空数组。只记「现在」,一个人离开,就把他从这个字段里拿掉。
  - **怎么算在看**:前端开着这个 work 时定时发心跳(沿用现在的 touch,120 秒一个窗口)。心跳时间只放在进程内存里(work → 人 → 最后一次心跳),**不进库**;超过窗口没心跳的人,由服务定时清出 `viewers`。前端关页面时主动发一次「离开」,就不用等超时。服务重启时把所有 work 的 `viewers` 清空:重启那一刻,谁也没在看。
  - **不再有「谁动过」的历史名单。** 以前的 `work_users`(谁动过、第一次 / 最后一次、动了几次)去掉。这个问题交给轨迹回答:每个段、每个点都带 `user_id`(§5),「谁在这个 work 上做过什么、最近一次是什么时候」就是 `worktrace.db` 里按 `work_id` 查、按 `user_id` 聚合。
  - **为什么一个字段就够了。** 里面就是几个名字,名字本身没有要单独改的属性;它也不是真相来源,只是内存里心跳表的投影。唯一要守住的一点:**只能由服务按内存的心跳表整份算出来再写,不能读出来追加一个名字再写回去**,否则两个人同时发心跳就会互相覆盖。偶尔要查「alice 现在在看哪些 work」,用 sqlite 的 `json_each` 展开就行。
- **`inbox`**:字段就是 `InboxItem` 的字段。原来的 `unmanaged.jsonl` 就是 `work_id` 为空的那些行。它放在 `works.db` 而不是 `worktrace.db`:收件箱是别的地方打给这个 work、等着处理的消息,属于「现在」;轨迹记的是这个 work 自己做过什么。
- **以后**:[work-trace.md §7](work-trace.md) 的计划会给 `works` 加 `plan_start` / `plan_due` 两列;依赖另开一张 `work_deps`(`work_id`, `depends_on`),主键是这两列的组合。

## 4. 列:弱编排——work_columns + worklets 上的位置

**一个 work 有几列(有序、可起别名、可收起),每个工作单元摆在某一列的某个位置——编排就这么多,没有别的布局对象。** 存下来的是三样:`work_columns`(有哪些列、什么顺序)、`worklets` 自己的 `column_number` / `position` / `collapsed`(每个工作单元在哪一列第几个、收没收起)、`works.next_column`(下一列的编号)。工作单元的位置不另立一个东西:一个工作单元只在一个位置,位置的属性就直接是工作单元那一行的列。怎么铺开、多宽多高,是前端的事。

```
work_columns
 work_id   number  alias   collapsed  position
 w…1002    1       ""      0          0
 w…1002    3       "测试"  0          1

worklets(只列和位置有关的列)
 id           work_id  column_number  position  collapsed
 w…1002-w1    w…1002   1              0         0
 w…1002-w3    w…1002   1              1         1
 w…1002-w4    w…1002   3              0         0
```

- **列的身份是 (`work_id`, `number`)**。对外的 id `c<number>` 是拼出来的,不存;只认这一种写法(`c(\d+)` 整串匹配,`c01` 这种也不算),别的一律 404。`number` 由 `works.next_column` 发,永不改、不复用([work-events.md §3](work-events.md))。
- **位置是工作单元可以改的属性,不是它的身份。** [worklet.md §2](worklet.md) 要的是「换个位置还是它」:挪到别的列,改的是这一行的 `column_number` / `position`,`id` 不动,轨迹和出处都不断。位置放在同一行,身份照样不挂在位置上。
- **`column_number` 为空 = 登记了、但不在任何一列**(worklet.md §3 允许这种情况;对外 `column` / `position` 是 `null`,前端把它摆在最左一列)。正常流程是打开就放进一列、关闭就连行一起删掉,所以平时不会为空;挪、收起这样一个工作单元 → 404。
- **一个工作单元只在一个位置**:这是结构本身决定的,一行只有一组位置。worklet.md §7 留着的「一个工作单元能不能同时摆在两处」(同一个终端镜像两份),到这里就定成了**不能**。真要镜像,再单开一张表。
- **顺序用 `position`**:列从左到右是 0、1、2……;同一列的工作单元从上到下也是 0、1、2……。**同一个 work 的列、同一列的工作单元,position 始终是连续的**(没有空洞、不重复)。每个动作在同一个事务里把受影响的那几行挪一下,保持这一点。行数很少,每次挪几行没有负担;换来的是「第几个」就是 `position`,查询不用再算。
- **至少一列**:新 work 建的时候就插一列 `number = 1`,不再靠「读的时候补」。

每个动作在一个事务里做完。列的动作交回动完的列清单(和动作在同一个事务里读),挪 / 收起工作单元交回工作单元清单,打开交回这个工作单元(带它在哪一列第几个);没有版本号,前端拿交回的清单直接替换本地的:

| 动作 | 改哪些行 |
|---|---|
| 加一列(在 `cX` 右边) | `works.next_column` 取号并 +1;`cX` 右边的列 `position + 1`;插一行新列 |
| 改别名 / 收起列 | 改 `work_columns` 那一行 |
| 删空列 | 先确认没有工作单元的 `column_number` 是它(有就 409),也不是最后一列(是就 409);删掉这行;它右边的列 `position − 1` |
| 打开工作单元(放进 `cX`) | 插一行 worklet,`column_number = X`(不给列 = `position` 为 0 的那列),`position` = 这列现有的个数 |
| 挪工作单元 | 原列里它下面的 `position − 1`;目标列里 `≥ index` 的 `position + 1`(`index` 按先从原列拿掉之后数,超出 / 不给 = 末尾);改它自己的 `column_number` 和 `position` |
| 收起工作单元 | 改它的 `collapsed` |
| 关闭工作单元 | 删这一行 worklet;原列里它下面的 `position − 1` |

**现在能直接查了**,不用再把 JSON 拍平:

```sql
-- 列 3 里有哪些工作单元,从上到下
SELECT id, uri FROM worklets WHERE work_id = ? AND column_number = 3 ORDER BY position;

-- 某个工作单元在哪一列、第几个
SELECT column_number, position FROM worklets WHERE id = ?;

-- 每一列有几个工作单元(包括空列)
SELECT c.number, c.alias, COUNT(w.id)
  FROM work_columns c LEFT JOIN worklets w
    ON w.work_id = c.work_id AND w.column_number = c.number
 WHERE c.work_id = ? GROUP BY c.number ORDER BY c.position;

-- 所有 work 里,别名叫「测试」的列上开着的终端
SELECT w.id FROM worklets w JOIN work_columns c
    ON c.work_id = w.work_id AND c.number = w.column_number
 WHERE c.alias = '测试' AND w.scheme = 'bash';
```

对外就是两份清单,各一次查询,不再拼成一份:`GET /works/{id}/columns` 是列(`{id: "c<number>", alias, collapsed, position}`,按 `position` 从左到右);`GET /works/{id}/worklets` 是工作单元(按编号,也就是开的先后),每个带 `column`(`c<column_number>`,不在任何一列 = `null`)/ `position` / `collapsed`。列和位置是「现在是什么样子」:不从轨迹重放出来,也不从它 diff 出轨迹。

## 5. worktrace.db:work 的全部轨迹

**原来的 `events` 流整个搬到这里,换成 work-trace.md 的「段 + 点」。** 字段按 OTel 的 span / log record **一对一**存:id 是十六进制字符串,时间是 Unix 纳秒整数,属性是 OTLP 的 `KeyValue` 列表(JSON)。所以任何一行都能无损拼回一个 OTLP/JSON 的 span 或 log record。落盘是按列存的,方便按 work、按时间查;对外(`GET /works/{id}/trace`、OTLP 导出)时再拼成标准的信封。

| 表 | 主键 | 列 | 说明 |
|---|---|---|---|
| `spans` | `span_id` | `trace_id`(索引)、`parent_span_id`、`work_id`(索引)、`worklet_id`(索引)、`user_id`(索引,开段的人)、`end_user_id`(索引,结束它的人)、`name`、`kind`、`start_time_unix_nano`、`end_time_unix_nano`、`status_code`、`attributes`(JSON)、`links`(JSON)、`first_round_id`(只有 `agent.turn` 有) | 段:`work` / `worklet` / `agent.turn`。**`end_time_unix_nano` 为空 = 还开着**。结束 = 在同一行填上终点和结束时的属性;`agent.turn` 按 `first_round_id` 幂等改(work-trace.md §2) |
| `points` | `seq`(自增) | `trace_id`、`span_id`(索引)、`work_id`(索引)、`worklet_id`、`column_number`、`user_id`(索引)、`event_name`(索引)、`time_unix_nano`、`attributes`(JSON) | 点:`column.*`、`worklet.moved`、`worklet.closed`、`work.renamed`(以后还有 `plan.changed`),只追加 |
| `rounds` | `seq`(自增) | `work_id`、`worklet_id`(索引)、`round_id`、`timestamp`、`role`、`text` | agent 工作单元的 round(原来的 `rounds.jsonl`),按 (`worklet_id`, `round_id`) 去重(进程内一把锁),按 `seq` 读。`agent.turn` 段通过 round id 引用它(现在;改完去掉,见下) |

> **按 [work-node.md](work-node.md) 改完的样子(未实施)**:`rounds` 表和 `spans.first_round_id` 去掉——agent 的每条消息是一个点(`agent.message` / `agent.tool.input` / `agent.tool.output`),正文进 `points.body`,带 `uid`(按它去重)和 `observed_time_unix_nano`;段多了 `agent.session` / `agent.tool`,`agent.*` 都由节点经 `POST /api/works/{id}/trace` 推、结束即定稿;另加一张 `trace_cursors`(每个工作单元每份来源推到哪了)。逐列见 [structure worktrace.md](../../structure/v5/worktrace.md)。

几条规则:

- **常用的属性提成列,完整的属性另存一份。** OTel 的属性是开放的键值,每种段、每种点带的都不一样,没法全部变成固定的列;所以 `attributes` 保留完整的 OTLP `KeyValue` 列表,只用来导出和拼回 OTLP,查询不碰它。平时要筛的维度(哪个工作单元、谁、哪一列、什么事件)都提成真的列:`worklet_id`、`user_id`、`column_number`、`event_name`。以后再冒出常查的属性,就再提一列。
- **开着的段就是一行没有终点的记录。** work-trace.md §3 为这个问题另外开了一份 `spans` doc(因为 jsonl 只能追加一整条);到了表里,「开着」只是一列为空,不用再单独存一份状态。**只追加的是 `points` 和 `rounds`;`work` / `worklet` 段每行最多改一次**,就是结束那次;`agent.turn` 段随着新 round 同步进来原地改(最后一条 round、条数、终点)——这是现在;按 work-node.md 改完,`agent.*` 段由节点按收尾标记结束,结束即定稿。
- **user 的统计也从这里来**:「动过哪些 work、最近一次什么时候」= `spans.user_id` / `spans.end_user_id` / `points.user_id` 按人查(都有索引),见 user.md §3。
- **一个 work 的轨迹** = `work_id = ?` 的段和点;**一棵树的轨迹** = 同一个 `trace_id`(work-trace.md §4)。两个都有索引。
- **agent 的对话放在这里**,是因为它和段、点的性质一样:只追加、量大、是「经过」。放进 `works.db` 会让状态库越长越大,备份也越来越慢。
- `GET /works/{id}/trace` 开着的段也给(没有终点,带 `memorytalk.open = true`)。往外导出(还没做)只发**已经结束**的段(OTLP 没有「开着的 span」),点随写随发,见 work-trace.md §8。

## 6. 一个动作写了哪几处

以「在 列 3 打开一个终端」为例:

1. 先验:work 没归档(归档了 409),列在不在(查 `work_columns`;不在直接 404,不建现场),URI 解析得出协议(解析不了 400,号也不取)
2. **`works.db` 一个短事务:取号**。`works.next_worklet` 取出 n 并 +1,工作单元 id = `<work_id>-w<n>`,`created_at` = 此刻。现场要拿这个 id 当名字(tmux 会话名),所以号得在建现场之前取
3. **建现场**(tmuxd,id 就是上一步的 id,`since_mtime` = `created_at` 的 Unix 秒);建不起来到此为止,除了那个号什么都没写——**号不还**,下一个工作单元接着往后发(编号本来就允许有空洞)
4. **`works.db` 一个事务**:先再看一眼 work 有没有在建现场的这会儿被归档(归档了就 409,现场销毁掉,什么都不写;不然归档时还没登记的它躲过了冻结,会在归档的 work 里留一个活的现场);`worklets` 插一行(`uri` 是原样的 uri,`cwd` 取现场报回来的),顺带定好位置(`column_number = 3`,`position` = 列 3 现有的个数;没给列就放 `position` 为 0 的那列)
5. **`worktrace.db`**:`spans` 插一行 `worklet` 段(开着,父是这个 work 最新的 `work` 段;带 uri / scheme / server 和放进的列)。失败只记日志,工作单元照样开好;交回的工作单元带 `column` / `position`(`c3`,列 3 原来的个数)

两步写要注意:

- **两个库之间没有原子提交。** 两个库都是 WAL 模式,sqlite 在 WAL 下即使 `ATTACH` 在一起,跨库事务也只保证每个库各自原子,不保证两个库一起提交。所以顺序固定为**先 `works.db`,后 `worktrace.db`**。后一步失败的话,轨迹少一段,work 本身没问题。这和「轨迹丢了不伤 work」是同一个取舍。
- **同一个 work 的生命周期动作排队。** 归档要先让节点把记录推完、逐个销毁现场,最后才结束段;这中间 `works.db` 里已经是 `archived`,段却还开着。要是这时有人把它重新打开,归档最后会去结束重新打开后的那一段,原来那段永远开着;刚登记、还没开段的工作单元也会在归档后才开出一段。所以归档 / 重新打开(从改状态的事务到收尾做完)、打开工作单元(第 4 步到第 5 步)、重入,在服务里按 work 拿一把进程内的锁一个一个来;打开和重入都在锁里再看一眼 work 是不是已归档(归档了 409),等着归档做完的那个醒来就不会在归档的 work 里起现场、开段。这是 Python 的锁,不是 `works.db` 的事务:建现场、销毁现场、写 `worktrace.db` 照样不在事务里。兜底:归档结束这个 work 所有还开着的 work 段;重新打开时上一段还开着(那次轨迹没写进去),先按归档补上终点(work-trace.md §5)。
- **现场和登记之间也不是原子的。** 把建现场挪到登记之前,是为了失败时什么都不用回滚(上一版是先登记、建失败再删),代价只是烧掉一个号。反过来,现场建起来了但第 4 步失败(比如列刚好被删了、work 刚好被归档了),就顺手把现场销毁再报错;连销毁也失败的,会留下一个没有登记的 tmux 会话,这种会话启动时对一遍就能收掉,和 work-trace.md §5「现场没了的段」是同一个对账过程,方向相反(启动时的对账还没做:现在「现场没了」只在列清单时发现)。

## 7. 从上一版怎么过来

**不做兼容。** 上一版的 `works/` 目录树、`memory.sqlite` 里的 `works` / `work_docs` / `work_logs` 三张表,实施时都不再读。现有实例的 work 数据不迁移,重新开始(和切换到 tmuxd 3.0 时对待 8090 实例的做法一样)。

provider 补上的能力(provider.md):**组合主键**(`db.table(..., primary_key=("work_id", "number"))`,`work_columns`)和**多列索引**(`indexes=[("work_id", "column_number", "position")]`,`worklets`);另外 `is_not_null()`、bool 列读回 Python 的 bool、`ORDER BY` 多列、`SET col = col + n`(挪位置、计数器取号)。position 上**不加** UNIQUE 索引:sqlite 在 `position = position + 1` 的过程中逐行查重,会撞上还没挪的那一行。外键不加,由单写者和事务保证。

已经删掉的东西:`FsWorkRepo`、`DbWorkRepo` 和 doc / log 的通用写法(`get_doc` / `put_doc` / `append` / `read`)、`MEMORY_TALK_STORE` 对 work 的作用、旧状态值和 `done_at` 的兼容、列的 `name` 别名、读列时补列 / 重排、扫事件补工作单元编号、`seq` doc、`frozen` 事件。后来又去掉了原来的画布:`GET /works/{id}/canvas` 那份把列和工作单元拼在一起的读视图、`Canvas` / `Panel` 模型和 `works.canvas_version`(已有的 `works.db` 里这一列还在,不再读写),只剩 §4 的列和位置。测试的 `home` 仍按 fs / sqlite 双跑,那个开关现在只管 users / auth。同步改了的文档:user.md §3(work 上的 `users` 名单变成只记现在的 `viewers`,历史改从轨迹查;`GET /works/{id}/users` 只剩 `current`)、provider.md(work 不再用文件系统族)、`structure/v5/filesystem.md`(`works/` 目录没了,换成两个 db 文件)、`structure/v5/work.md`、work-trace.md §3(落盘改成 §5 的 `spans` / `points` / `rounds`)。

## 8. 这篇有意不定的事

- **users / auth 放哪。** 它们现在跟着 `MEMORY_TALK_STORE` 走(fs 下是 `users/`、`auth/tokens/`,sqlite 下在 `memory.sqlite` 里)。它们不属于 work。倾向:同样只留 sqlite,单独一个 `users.db`,或者并进 `works.db`。放进 `works.db` 能少一个文件,但 users 本来就不是 work 的信息。到时候单独定。
- **worktrace.db 怎么变老。** 轨迹会一直涨。可以按时间切(`worktrace-2026Q4.db`,查询时 `ATTACH`),也可以把已结束的 work 的轨迹导出成 OTLP/JSON 文件归档,再从库里删掉。先不做,等体量真大了再定。
- **agent 的消息要不要再单独一个库。** 消息正文是轨迹里最大的一块。如果它把段和动作点的查询拖慢了,再把 `agent.*` 点拆到单独的表或库。列不用变,只是换个地方(work-trace.md §10)。
- **多进程。** 两个库都只由服务进程写。CLI 和 agent 都走 HTTP API,不直接开库。
