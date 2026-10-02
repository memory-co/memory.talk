# worktrace.db —— work 的经过:spans / points / trace_cursors

`<HOME>/worktrace.db`(`MEMORY_TALK_WORKTRACE_DB` 可改),sqlite,WAL。装 work 的**经过**:有起止的是**段**(work、工作单元,agent 的会话 / 轮次 / 工具调用),一个时刻的事是**点**(人的动作、agent 的每条消息、状态变化)。**没有 round 这个单独的东西**:一条消息就是一个点,正文在点的 `body` 里。**现在**(work、列、工作单元登记)在 `works.db`,见 [work.md](work.md#存储)。模型和为什么见 [designs work-trace.md](../../designs/v5/work-trace.md);谁往里写、怎么推见 [designs work-node.md](../../designs/v5/work-node.md);读和写都走 `/api/works/{id}/trace`。

> **状态:定下来的表设计,代码还没跟上。** 现在库里还多一张 `rounds` 表、`spans` 多一列 `first_round_id`,`points` 还没有 `uid` / `observed_time_unix_nano` / `body`,也还没有 `trace_cursors`;按 [work-node.md §11](../../designs/v5/work-node.md) 第 2 步实施时一起改,不迁移(§6)。

---

## 1. 总览

```
spans ──parent_span_id──▶ spans      段的父子:work → 子 work / worklet → agent.session → agent.turn → agent.tool
  ▲
  └──── span_id ──────── points      点挂在哪一段:动作点挂 work / worklet 段,消息挂轮次段,工具的参数和结果挂工具段
trace_cursors(worklet_id, source)     每个工作单元每份来源推到哪了
work_id / worklet_id ──▶ works.db 的 works.id / worklets.id(跨库,不设外键)
```

| 表 | 一行是 | 写法 |
|---|---|---|
| `spans` | 一个段:`work` / `worklet` / `agent.session` / `agent.turn` / `agent.tool` | 按 `span_id`:没有就插(终点为空 = 开着);开着的收到终点就补上,收到开着的就合并属性;结束了的不再动。每次开、改都取新的 `seq` |
| `points` | 一个点:动作点(`work.renamed` / `column.*` / `worklet.moved` / `worklet.closed` / `worklet.input`)或 agent 点(`agent.message` / `agent.tool.input` / `agent.tool.output` / `agent.state`) | 只追加;带 `uid` 的按它去重。写入时取新的 `seq` |
| `trace_cursors` | 一个工作单元的一份来源推到哪了 | 和推上来的数据同一个事务写 |

**一条写路径。** 只有一个写入函数,收 OTLP/JSON 的段和点——和 `GET /api/works/{id}/trace` 读出来的是同一个形状。中心自己的动作(人建 work、开工作单元、挪列……)直接调它;节点经 `POST /api/works/{id}/trace` 调它([work-node.md §6](../../designs/v5/work-node.md))。哪些记录归中心写、哪些归节点写,见 [designs work-trace.md §5](../../designs/v5/work-trace.md)。

共同约定:

- **id 是小写十六进制串**:trace id 32 位(16 字节),span id 16 位(8 字节),都由身份算出来(§2),不随机。
- **时间都是 Unix 纳秒**,`INTEGER`(64 位,到 2262 年都够);对外写成十进制字符串。agent 的记录里各家时间格式不一样,由节点换算好再推。
- **`attributes` / `links` 是 OTLP 的 JSON**,存成文本:`attributes` 是 KeyValue 列表 `[{"key": …, "value": {"stringValue" | "intValue"(十进制串)| "boolValue" | "doubleValue": …}}]`,值为空的键不写;`links` 是 `[{"traceId", "spanId", "attributes": []}]`。`body` 存正文文本(对外是 `{"stringValue": …}`)。
- **提升列**:要拿来查的值从属性里提出来另存一列(`user_id`、`end_user_id`、`worklet_id`、`column_number`、`uid`),JSON 里照样留着;对外只用 JSON。`work_id` 是存储用的列,不一定在属性里。
- **没有外键**:`work_id` / `worklet_id` 指向 `works.db`,跨库约束不了;工作单元关掉后 `worklets` 里那一行删了,轨迹里的 id 照样留着——经过比现在活得久。
- **一个变更序号,两张表共用**:`spans.seq` 和 `points.seq` 取自同一个序号——写入函数在同一个事务里取「两张表现有的最大值 + 1」(只有中心这一个写者,不会撞)。段记它最后一次改动(开、合并、结束)的序号,点记写入时的序号。`GET …/trace?after=<seq>` 就靠它接住所有变化:读 output、看对话、界面等变化,都是这一个游标。
- **不删**:三张表都没有删除路径。

---

## 2. spans:段

```sql
CREATE TABLE spans (
  span_id              TEXT PRIMARY KEY,
  trace_id             TEXT,
  parent_span_id       TEXT,
  work_id              TEXT,
  worklet_id           TEXT,
  user_id              TEXT,
  end_user_id          TEXT,
  name                 TEXT,      -- work / worklet / agent.session / agent.turn / agent.tool
  kind                 INTEGER,
  start_time_unix_nano INTEGER,
  end_time_unix_nano   INTEGER,   -- 空 = 还开着
  status_code          INTEGER,
  attributes           TEXT,      -- OTLP KeyValue 列表(JSON)
  links                TEXT,      -- OTLP Link 列表(JSON)
  seq                  INTEGER    -- 最后一次改动的变更序号(和 points 共用一个序号)
);
CREATE INDEX idx_spans_trace_id    ON spans(trace_id);
CREATE INDEX idx_spans_work_seq    ON spans(work_id, seq);
CREATE INDEX idx_spans_worklet_id  ON spans(worklet_id);
CREATE INDEX idx_spans_user_id     ON spans(user_id);
CREATE INDEX idx_spans_end_user_id ON spans(end_user_id);
```

| 列 | 空 | OTLP | 什么时候写 | 说明 |
|---|---|---|---|---|
| `span_id` | 否 | `spanId` | 开 | 由身份算,取 sha256 的前 16 位:`work` = `"memorytalk/span/work/<work id>/<第几段>"`;`worklet` = `…/span/worklet/<worklet id>/<第几段>`;`agent.session` = `…/span/session/<worklet id>/<会话 id>/<这一段第一条记录的 uid>`;`agent.turn` = `…/span/turn/<worklet id>/<这一轮人那条输入的 uid>`;`agent.tool` = `…/span/tool/<worklet id>/<调用 id>`。「第几段」= 已有几段同名的段,从 0 起。前两种中心算,后三种节点算 |
| `trace_id` | 否 | `traceId` | 开 | `sha256("memorytalk/trace/<根 work id>")` 前 32 位:一棵 work 树一条 trace |
| `parent_span_id` | 是 | `parentSpanId` | 开 | `work`:父 work 最新的一段 `work` 段,根 work 为空;`worklet`:所在 work 最新的一段 `work` 段;`agent.session`:所在工作单元最新的一段 `worklet` 段;`agent.turn`:所在会话段;`agent.tool`:所在轮次段(子 agent 的轮次挂在派它的那个工具段下面) |
| `work_id` | 否 | —(`work` / `worklet` 段另有属性 `memorytalk.work.id`) | 开 | 属于哪个 work;节点推的取请求路径上的 work |
| `worklet_id` | 是 | 属性 `memorytalk.worklet.id` | 开 | 除 `work` 段外都有 |
| `user_id` | 是 | 属性 `user.id` | 开 | 开它的人(建 / 重新打开 work、打开 / 重入工作单元的人);没带身份为空;`agent.*` 永远为空(那是 agent 的) |
| `end_user_id` | 是 | 属性 `memorytalk.end.user.id` | 结束 | 结束它的人;开着、`gone`、重新打开时补记的归档(不知道是谁)、`agent.*` 都为空 |
| `name` | 否 | `name` | 开 | 见上面的五种 |
| `kind` | 否 | `kind` | 开 | 恒为 1(INTERNAL) |
| `start_time_unix_nano` | 否 | `startTimeUnixNano` | 开 | 动作发生的时刻;`agent.*` 取记录里的时刻(会话 = 第一条记录,轮次 = 人那条输入,工具 = 调用那条) |
| `end_time_unix_nano` | 是 | `endTimeUnixNano` | 结束 | **空 = 还开着**,不另存「开着」的状态;读的时候开着的段不出 `endTimeUnixNano`,另加属性 `memorytalk.open = true`(写的时候不用带) |
| `status_code` | 否 | `status.code` | 开 / 结束 | 0 = Unset(开着;`gone` 结束的段和跟着它结束的子段也保持 0);1 = OK(正常结束);2 = Error(只有结果标了出错的工具调用) |
| `attributes` | 否 | `attributes` | 开;开着时合并;结束时合并 | 开着的段收到新的开着版本,同名的键以新的为准(比如这一轮的消息数在涨);结束时并进结束的属性(`memorytalk.end.reason`、`memorytalk.end.user.id`,`worklet` 段另有 `memorytalk.end.column.id` / `.alias`)。各段有哪些键见 [designs work-trace.md §2、§4、§5](../../designs/v5/work-trace.md) |
| `links` | 否 | `links` | 开 | 重新打开的 `work` 段指向上一段;`/resume` 回来的 `agent.session` 段指向这个会话的上一段;其余是 `[]` |
| `seq` | 否 | — | 开 / 合并 / 结束 | 最后一次改动的变更序号(§1);`GET …/trace?after=` 靠它找出改过的段 |

按 `name` 看哪些列有值:

| `name` | 谁写 | `worklet_id` | `parent_span_id` | `user_id` / `end_user_id` | `links` |
|---|---|---|---|---|---|
| `work` | 中心 | 空 | 父 work 的 `work` 段(根为空) | 有 | 重新打开的那段有 |
| `worklet` | 中心;`gone` 的结束由节点补 | 有 | 所在 work 的 `work` 段 | 有(`gone` 没有结束的人) | `[]` |
| `agent.session` | 节点 | 有 | 所在工作单元的 `worklet` 段 | 都空 | `/resume` 回来的有 |
| `agent.turn` | 节点 | 有 | 所在会话段 | 都空 | `[]` |
| `agent.tool` | 节点 | 有 | 所在轮次段 | 都空 | `[]` |

**怎么改**(写入函数按 `span_id` 处理每一条段):

- **库里没有** → 插一行;没有终点就是开着。id 由身份算,同一段推几次都是同一个 id,不会多出一行。
- **库里有、还开着,收到的带终点** → 在事务里补上终点、status、`end_user_id`,合并结束的属性;两处同时结束同一段,先到的算数。
- **库里有、还开着,收到的也开着** → 只合并属性。
- **库里有、已经结束** → 跳过。**所有段结束即定稿**,包括 `agent.turn`(节点按 agent 自己的收尾标记结束它)。
- **不变式**(由写入路径保证,表上没有约束):一个 work 同时最多一段 `work` 段开着;一个工作单元同时最多一段 `worklet` 段、一段 `agent.session` 段开着;一个会话同时最多一轮开着。

---

## 3. points:点

```sql
CREATE TABLE points (
  seq                     INTEGER PRIMARY KEY,   -- 变更序号,和 spans 共用(§1),由写入函数发
  uid                     TEXT UNIQUE,
  trace_id                TEXT,
  span_id                 TEXT,
  work_id                 TEXT,
  worklet_id              TEXT,
  column_number           INTEGER,
  user_id                 TEXT,
  event_name              TEXT,
  time_unix_nano          INTEGER,
  observed_time_unix_nano INTEGER,
  body                    TEXT,
  attributes              TEXT       -- OTLP KeyValue 列表(JSON)
);
CREATE INDEX idx_points_span_id     ON points(span_id);
CREATE INDEX idx_points_worklet_seq ON points(worklet_id, seq);
CREATE INDEX idx_points_work_seq    ON points(work_id, seq);
CREATE INDEX idx_points_user_id     ON points(user_id);
CREATE INDEX idx_points_event_name  ON points(event_name);
```

| 列 | 空 | OTLP | 说明 |
|---|---|---|---|
| `seq` | 否 | — | 写入时的变更序号,和 `spans.seq` 共用一个序号(§1);读按它排,`after=` 的游标 |
| `uid` | 是 | 属性 `log.record.uid` | 节点推的点都有:`<worklet id>:<来源里的消息 id>`,一条记录里有几块内容时再加 `:<第几块>`(来源里的消息 id:Claude Code 的 `uuid`、Codex 的 `<rollout 文件名>:<行号>`、Kimi 的事件 `uuid`)。唯一,有了就跳过;认知层引用一条消息也用它。中心写的动作点为空(sqlite 的 `UNIQUE` 允许多个空) |
| `trace_id` | 否 | `traceId` | 所在 work 树的 trace |
| `span_id` | 是 | `spanId` | 挂在哪一段:`work.renamed` / `column.*` 挂 work 最新的 `work` 段;`worklet.moved` / `worklet.closed` / `worklet.input` 挂这个工作单元最新的 `worklet` 段;`agent.message` 挂它那一轮(第一条人的输入之前的挂会话段);`agent.tool.*` 挂那次调用的工具段;`agent.state` 挂会话段。那一段不存在时为空 |
| `work_id` | 否 | — | 属于哪个 work |
| `worklet_id` | 是 | 属性 `memorytalk.worklet.id` | `worklet.*` 和 agent 点有 |
| `column_number` | 是 | 属性 `memorytalk.column.id` 的编号(`c3` → 3) | 这个点关于哪一列:`column.*` 是那一列,`worklet.moved` 是挪去的那列,`worklet.closed` 是关的时候所在的列;其余为空 |
| `user_id` | 是 | 属性 `user.id` | 谁做的;没带身份、agent 点为空 |
| `event_name` | 否 | `eventName` | 动作点:`work.renamed` / `column.added` / `column.renamed` / `column.removed` / `worklet.moved` / `worklet.closed` / `worklet.input`;agent 点:`agent.message` / `agent.tool.input` / `agent.tool.output` / `agent.state`。各自的属性见 [designs work-trace.md §2](../../designs/v5/work-trace.md) |
| `time_unix_nano` | 否 | `timeUnixNano` | 事情发生的时刻:动作点是动作那一刻,agent 点是记录里的时刻 |
| `observed_time_unix_nano` | 否 | `observedTimeUnixNano` | 中心收到的时刻(请求里带的不算);中心自己写的点和上一列相同 |
| `body` | 是 | `body` | 正文:`agent.message` 的消息、`agent.tool.input` 的调用参数、`agent.tool.output` 的结果;其余为空 |
| `attributes` | 否 | `attributes` | 含 `user.id`、`log.record.uid` |

**只追加**:插了就不改、不删。

---

## 4. trace_cursors:推到哪了

```sql
CREATE TABLE trace_cursors (
  worklet_id TEXT,
  source     TEXT,
  position   TEXT,
  updated_at TEXT,
  PRIMARY KEY (worklet_id, source)
);
```

| 列 | 说明 |
|---|---|
| `worklet_id` | 哪个工作单元 |
| `source` | 哪一份来源:agent 的会话 id(一份会话记录),或 `hooks`(节点本地的 hooks 事件文件) |
| `position` | 读到哪了:文件偏移或最后一条的 id。只有节点懂,中心原样存、原样给 |
| `updated_at` | 最后一次写的时刻(ISO 8601) |

- **跟数据同一个事务**:`POST …/trace` 请求里的 `cursors` 一栏,和这次的段、点一起提交,一行一个 (`worklet_id`, `source`),有就改、没有就插。
- **中心说了算**:节点连上(或重连)时用 `GET /api/works/{id}/trace?worklet=…&fields=cursors` 读回来,从那里接着读、接着推;推重复了由 `span_id` / `uid` 去重,所以游标落后一点也没关系。

---

## 5. 读写纪律和查询

- **只有中心进程打开这个库**:节点不碰库,经 `POST …/trace` 交给中心写;WAL 模式,读不挡写。
- **一次请求一个事务**:节点的一次 `POST` 是一个事务(段、点、游标一起)。中心自己的动作先在 `works.db` 里做完,再写这里;这里写失败只记日志,不回滚 work(两个库之间没有原子提交)。
- **「查一下再写」在事务里**:第几段、开没开着、按 id / uid 有没有,都在 `worktrace.db` 的一个事务里;要读 `works.db` 的(trace id 要走到根)在事务外先算好。

| 查询 | 谁用 | 条件 / 顺序 | 走的索引 |
|---|---|---|---|
| 按 id 找段 | 写入时合并 / 结束 | `span_id = ?` | 主键 |
| 按 uid 去重 | 写入时插点 | `uid` 冲突就跳过 | `uid` 的唯一索引 |
| 一个 work 的 `work` 段 | 算第几段、找最新的 `work` 段 | `work_id = ? AND name = 'work'`,按 (`start_time_unix_nano`, `span_id`) | `idx_spans_work_seq`(用前缀 `work_id`) |
| 一个 work 开着的段 | 归档、重新打开 | `work_id = ? AND name = ? AND end_time_unix_nano IS NULL` | `idx_spans_work_seq`(用前缀 `work_id`) |
| 一个工作单元的段 | 找最新的 `worklet` 段、重入;它的会话 / 轮次 / 工具 | `worklet_id = ? AND name = ?` | `idx_spans_worklet_id` |
| 一组 work 的段和点 | `GET …/trace`(`subtree` 时是全部子孙 work);默认不给 agent 点、不取 `body` | `work_id IN (…)`;段按开始时间,点按时间再按 `seq` | `idx_spans_work_seq`、`idx_points_work_seq` |
| 读变化(output、看对话、界面等变化) | `GET …/trace?…&after=<seq>&wait=`,可加 `worklet=` / `agent=1` / `bodies=1` | `work_id IN (…)`(或 `worklet_id = ?`)`AND seq > ?`,按 `seq` | `idx_spans_work_seq`、`idx_points_work_seq`、`idx_points_worklet_seq` |
| 一段下面的点 | 一轮的消息、一次工具调用的参数和结果 | `span_id = ?` | `idx_points_span_id` |
| 按类型筛 | 时间线里藏 / 显 agent 点 | `event_name` | `idx_points_event_name` |
| 某人出现过的 work | 用户页「动过哪些 work」 | `spans.user_id = ?`、`spans.end_user_id = ?`、`points.user_id = ?` | 三个 `user_id` 索引 |
| 推到哪了 | `GET …/trace?fields=cursors` | `worklet_id = ?` | `trace_cursors` 主键 |
| 整棵树 | 以后按树查(瀑布图 / 甘特图) | `trace_id = ?` | `idx_spans_trace_id` |

---

## 6. 还开着的

- **正文会让 `points` 大很多**。拖慢了列表和图的查询,就把 agent 点拆到单独的表或库,列不变([designs work-trace.md §10](../../designs/v5/work-trace.md))。
- **只增不减**:三张表没有清理路径,`worktrace.db` 会一直长;按时间切库还是导出后删,和 [designs work-store.md §8](../../designs/v5/work-store.md) 一起定。
- **实施时不迁移**:现在代码里的 `rounds` 表和 `spans.first_round_id` 直接删,已有的 round 不转成点,已有的 `agent.turn` 段留着不动。
