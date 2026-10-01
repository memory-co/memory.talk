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

- **仓储只有一份**,表可以按业务来设计。登记是一行一个工作单元(连同它摆在哪),画布的每一列也是一行,不再把一整个数组塞进一个 JSON;要查的字段都是真的列。
- **一个动作可以是一个事务**。「在列 3 打开终端」要改登记、计数器、画布三处,以前是三次独立的写,现在在 `works.db` 里一次提交(§6)。
- **没有目录扫描**。按父列子 work、按建的人筛,都走索引。

**为什么是两个库,不是一个:** 现在的状态和经过的轨迹,性质完全不一样。

| | `works.db`(现在) | `worktrace.db`(经过) |
|---|---|---|
| 装什么 | work 节点(含当前谁在看)、画布(列 / 格子)、登记、manager、收件箱 | 段、点(work-trace.md)、agent 的 round |
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

## 3. works.db 有哪些表

**原则:一张表一种东西,一行一个实体,要查的都是真的列,不存 JSON。** 画布没有自己的表:列是 `work_columns`,工作单元摆在哪是 `worklets` 自己的几列;收件箱的每个字段也拆成列。

```
works ──┬──< works          (parent:子 work)
        ├──< work_columns   (这个 work 的列)
        │        └──< worklets   (column_number + position:摆在哪一列第几个)
        └──< inbox          (收件箱;work_id 为空 = 没人管)
```

| 表 | 一行是 | 主键 | 其余列 |
|---|---|---|---|
| `works` | 一个 work | `id` | `parent`(索引)、`goal`、`status`、`created_by`(索引)、`created_at`、`archived_at`、`manager`、`viewers`、`next_worklet`、`next_column`、`canvas_version` |
| `work_columns` | 画布上的一列 | (`work_id`, `number`) | `alias`、`collapsed`、`position` |
| `worklets` | 一个工作单元 | `id` | `work_id`(索引)、`number`、`uri`、`scheme`、`server`、`cwd`、`created_at`、`last_attached`,**加上位置**:`column_number`、`position`、`collapsed` |
| `inbox` | 一条打过来的变动 | `seq`(自增) | `work_id`(索引,空 = 没人管)、`ts`、`layer`、`path`、`subject`、`sha`、`by`、`routed_by` |

各表说明:

- **`works`**:树就是 `parent` 列。`manager` 是这棵子树的变动打给谁(空 = 用父 work 的)。三个计数器:`next_worklet` 是下一个工作单元编号,`next_column` 是下一列编号,两个都单调递增、不复用;`canvas_version` 是画布版本号,每个画布动作 +1。
- **`work_columns`**:一列一行,见 §4。
- **`worklets`**:一个工作单元一行,既是登记,也记着它摆在画布的哪里。`number` 就是 id 里 `-w<n>` 的 n,单独存一列方便排序。位置那三列见 §4。
- **`works.viewers`:现在谁在看这个 work。** 一个字段,值是当前在看的人名(`["alice","bob"]`,按名字排);没人看就是空数组。只记「现在」,一个人离开,就把他从这个字段里拿掉。
  - **怎么算在看**:前端开着这个 work 时定时发心跳(沿用现在的 touch,120 秒一个窗口)。心跳时间只放在进程内存里(work → 人 → 最后一次心跳),**不进库**;超过窗口没心跳的人,由服务定时清出 `viewers`。前端关页面时主动发一次「离开」,就不用等超时。服务重启时把所有 work 的 `viewers` 清空:重启那一刻,谁也没在看。
  - **不再有「谁动过」的历史名单。** 以前的 `work_users`(谁动过、第一次 / 最后一次、动了几次)去掉。这个问题交给轨迹回答:每个段、每个点都带 `user_id`(§5),「谁在这个 work 上做过什么、最近一次是什么时候」就是 `worktrace.db` 里按 `work_id` 查、按 `user_id` 聚合。
  - **为什么这里允许一个字段装一组名字。** 这是 works.db 里唯一一个装列表的字段:人数很少,整份读、整份写,平时只在显示时用到。要查「alice 现在在看哪些 work」,用 sqlite 的 `json_each` 展开就行,不用单开一张表。
- **`inbox`**:字段就是 `InboxItem` 的字段。原来的 `unmanaged.jsonl` 就是 `work_id` 为空的那些行。它放在 `works.db` 而不是 `worktrace.db`:收件箱是别的地方打给这个 work、等着处理的消息,属于「现在」;轨迹记的是这个 work 自己做过什么。
- **以后**:[work-trace.md §7](work-trace.md) 的计划会给 `works` 加 `plan_start` / `plan_due` 两列;依赖另开一张 `work_deps`(`work_id`, `depends_on`),主键是这两列的组合。

## 4. 列布局存在哪:work_columns + worklets 上的位置

**画布 = `work_columns`(有哪些列、什么顺序)+ `worklets` 的 `column_number` / `position` / `collapsed`(每个工作单元摆在哪一列第几个)+ `works` 上的 `next_column` 和 `canvas_version`。** 画布没有单独的表,格子(panel)也没有:一个工作单元最多占一格,格子和工作单元是一对一的,格子的属性就直接是工作单元的列。

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

- **列的身份是 (`work_id`, `number`)**。对外的 id `c<number>` 是拼出来的,不存。`number` 由 `works.next_column` 发,永不改、不复用([work-events.md §3](work-events.md))。
- **位置是工作单元可以改的属性,不是它的身份。** [worklet.md §2](worklet.md) 要的是「换个格子还是它」:挪到别的列,改的是这一行的 `column_number` / `position`,`id` 不动,round 和出处都不断。把位置放在同一行,并不违背身份脱离布局。
- **`column_number` 为空 = 登记了、但没摆在画布上**(worklet.md §3 允许这种情况)。正常流程是打开就摆上、关闭就连行一起删掉,所以平时不会为空。
- **一个工作单元只能在一格里**:这是结构本身决定的,一行只有一组位置。worklet.md §7 留着的「一个工作单元能不能被多个格子装」(同一个终端在画布上镜像两份),到这里就定成了**不能**。真要镜像,再单开一张表。
- **顺序用 `position`**:列从左到右是 0、1、2……;同一列的工作单元从上到下也是 0、1、2……。**同一个 work 的列、同一列的工作单元,position 始终是连续的**(没有空洞、不重复)。每个动作在同一个事务里把受影响的那几行挪一下,保持这一点。行数很少,每次挪几行没有负担;换来的是「第几个」就是 `position`,查询不用再算。
- **至少一列**:新 work 建的时候就插一列 `number = 1`,不再靠「读的时候补」。

每个动作在一个事务里做完,并且都把 `works.canvas_version` +1:

| 动作 | 改哪些行 |
|---|---|
| 加一列(在 `cX` 右边) | `works.next_column` 取号并 +1;`cX` 右边的列 `position + 1`;插一行新列 |
| 改别名 / 收起列 | 改 `work_columns` 那一行 |
| 删空列 | 先确认没有工作单元的 `column_number` 是它(有就 409);删掉这行;它右边的列 `position − 1` |
| 打开工作单元(放进 `cX`) | 插一行 worklet,`column_number = X`,`position` = 这列现有的个数 |
| 挪工作单元 | 原列里它下面的 `position − 1`;目标列里 `≥ index` 的 `position + 1`;改它自己的 `column_number` 和 `position` |
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

对外的接口形状不变:`GET /works/{id}/canvas` 仍然返回 `{version, next_column, columns: [{id, alias, collapsed, panels: [{worklet, collapsed}]}]}`,由两次查询拼出来(列按 `position` 排,工作单元按 `column_number, position` 排)。`panels` 从此只是接口里的叫法,库里没有这个东西。画布仍然是快照:不从轨迹重放出来,也不从它 diff 出轨迹。

## 5. worktrace.db:work 的全部轨迹

**原来的 `events` 流整个搬到这里,换成 work-trace.md 的「段 + 点」。** 字段按 OTel 的 span / log record **一对一**存:id 是十六进制字符串,时间是 Unix 纳秒整数,属性是 OTLP 的 `KeyValue` 列表(JSON)。所以任何一行都能无损拼回一个 OTLP/JSON 的 span 或 log record。落盘是按列存的,方便按 work、按时间查;对外(`GET /works/{id}/trace`、OTLP 导出)时再拼成标准的信封。

| 表 | 主键 | 列 | 说明 |
|---|---|---|---|
| `spans` | `span_id` | `trace_id`(索引)、`parent_span_id`、`work_id`(索引)、`worklet_id`(索引)、`user_id`、`name`、`kind`、`start_time_unix_nano`、`end_time_unix_nano`、`status_code`、`attributes`(JSON)、`links`(JSON) | 段:`work` / `worklet` / `agent.turn`。**`end_time_unix_nano` 为空 = 还开着**。结束 = 在同一行填上终点和结束时的属性 |
| `points` | `seq`(自增) | `trace_id`、`span_id`(索引)、`work_id`(索引)、`worklet_id`、`column_number`、`user_id`、`event_name`(索引)、`time_unix_nano`、`attributes`(JSON) | 点:`column.*`、`worklet.moved`、`plan.changed`……只追加 |
| `rounds` | `seq`(自增) | `work_id`、`worklet_id`(索引)、`round_id`、`timestamp`、`role`、`text` | agent 工作单元的 round(原来的 `rounds.jsonl`)。`agent.turn` 段通过 round id 引用它 |

几条规则:

- **常用的属性提成列,完整的属性另存一份。** OTel 的属性是开放的键值,每种段、每种点带的都不一样,没法全部变成固定的列;所以 `attributes` 保留完整的 OTLP `KeyValue` 列表,只用来导出和拼回 OTLP,查询不碰它。平时要筛的维度(哪个工作单元、谁、哪一列、什么事件)都提成真的列:`worklet_id`、`user_id`、`column_number`、`event_name`。以后再冒出常查的属性,就再提一列。
- **开着的段就是一行没有终点的记录。** work-trace.md §3 为这个问题另外开了一份 `spans` doc(因为 jsonl 只能追加一整条);到了表里,「开着」只是一列为空,不用再单独存一份状态。**只追加的是 `points` 和 `rounds`;`spans` 每行最多改一次**,就是结束那次。
- **一个 work 的轨迹** = `work_id = ?` 的段和点;**一棵树的轨迹** = 同一个 `trace_id`(work-trace.md §4)。两个都有索引。
- **round 放在这里**,是因为它和段、点的性质一样:只追加、量大、是「经过」。放进 `works.db` 会让状态库越长越大,备份也越来越慢。
- 对外导出只发**已经结束**的段(OTLP 没有「开着的 span」),点随写随发。怎么导出见 work-trace.md §8。

## 6. 一个动作写了哪几处

以「在 列 3 打开一个终端」为例:

1. 先验列在不在(查 `work_columns`);不在直接 404,不建现场
2. **建现场**(tmuxd);建不起来到此为止,什么都没写
3. **`works.db` 一个事务**:`works.next_worklet` 取号 +1;`worklets` 插一行,顺带定好位置(`column_number = 3`,`position` = 列 3 现有的个数);`works.canvas_version + 1`
4. **`worktrace.db`**:`spans` 插一行 `worklet` 段(开着,父是这个 work 的 work 段)

两步写要注意:

- **两个库之间没有原子提交。** 两个库都是 WAL 模式,sqlite 在 WAL 下即使 `ATTACH` 在一起,跨库事务也只保证每个库各自原子,不保证两个库一起提交。所以顺序固定为**先 `works.db`,后 `worktrace.db`**。后一步失败的话,轨迹少一段,work 本身没问题。这和「轨迹丢了不伤 work」是同一个取舍。
- **现场和登记之间也不是原子的。** 把建现场挪到写库之前,是为了失败时什么都不用回滚(上一版是先登记、建失败再删)。反过来,现场建起来了但库写失败,就会留下一个没有登记的 tmux 会话;这种会话启动时对一遍就能收掉,和 work-trace.md §5「现场没了的段」是同一个对账过程,方向相反。

## 7. 从上一版怎么过来

**不做兼容。** 上一版的 `works/` 目录树、`memory.sqlite` 里的 `works` / `work_docs` / `work_logs` 三张表,实施时都不再读。现有实例的 work 数据不迁移,重新开始(和切换到 tmuxd 3.0 时对待 8090 实例的做法一样)。

provider 要补的能力:**组合主键**(`work_columns`)和**多列索引**(`worklets` 的 (`work_id`, `column_number`, `position`))。现在的 `Column(primary=True)` 只支持单列主键。外键不加,由单写者和事务保证。

要删掉的东西:`FsWorkRepo`、`DbWorkRepo` 里 doc / log 的通用写法、`MEMORY_TALK_STORE` 对 work 的作用、测试里 work 场景按 fs / sqlite 双跑的那一半参数。同时要改的文档:user.md §3(work 上的 `users` 名单变成只记现在的 `viewers`,历史改从轨迹查;`GET /works/{id}/users` 只剩 `current`)、provider.md(work 不再用文件系统族)、`structure/v5/filesystem.md`(`works/` 目录没了,换成两个 db 文件)、`structure/v5/work.md`、work-trace.md §3(落盘改成 §5 的两张表)。

## 8. 这篇有意不定的事

- **users / auth 放哪。** 它们现在跟着 `MEMORY_TALK_STORE` 走(fs 下是 `users/`、`auth/tokens/`,sqlite 下在 `memory.sqlite` 里)。它们不属于 work。倾向:同样只留 sqlite,单独一个 `users.db`,或者并进 `works.db`。放进 `works.db` 能少一个文件,但 users 本来就不是 work 的信息。到时候单独定。
- **worktrace.db 怎么变老。** 轨迹会一直涨。可以按时间切(`worktrace-2026Q4.db`,查询时 `ATTACH`),也可以把已结束的 work 的轨迹导出成 OTLP/JSON 文件归档,再从库里删掉。先不做,等体量真大了再定。
- **round 要不要再单独一个库。** agent 的 round 是三张表里最大的。如果它把 `spans` / `points` 的查询拖慢了,再拆成 `worktrace.db` + `rounds.db`。表结构不用变,只是换个文件。
- **多进程。** 两个库都只由服务进程写。CLI 和 agent 都走 HTTP API,不直接开库。
