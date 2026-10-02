# worktrace.db —— work 的经过:spans / points / rounds 三张表

`<HOME>/worktrace.db`(`MEMORY_TALK_WORKTRACE_DB` 可改),sqlite,WAL。装 work 的**经过**:段、点、agent 的 round;**现在**(work、列、工作单元登记)在 `works.db`,见 [work.md](work.md#存储)。为什么这么分、为什么是 OTel 的形状,见 [designs work-trace.md](../../designs/v5/work-trace.md) 和 [work-store.md §5](../../designs/v5/work-store.md);对外的 OTLP/JSON 见 [api works.md](../../api/v5/works.md)。

§1–§5 是**已实施**的样子(和 `services/work/repo.py` 的 `TraceRepo` 一致);§6 是已知问题和待改,**未实施**。

---

## 1. 总览

```
spans ──parent_span_id──▶ spans                  段的父子:work → 子 work / worklet → agent.turn
  ▲
  └──── span_id ──────── points                  点挂在哪一段
spans(agent.turn).first_round_id ──▶ rounds.round_id(同一个 worklet_id)
work_id / worklet_id ──▶ works.db 的 works.id / worklets.id(跨库,不设外键)
```

| 表 | 一行是 | 写法 | 谁写 |
|---|---|---|---|
| `spans` | 一个段(`work` / `worklet` / `agent.turn`) | 开的时候插一行,终点为空;结束时同一行补上终点 | `services/work/trace.py` |
| `points` | 一个点(`work.renamed` / `column.*` / `worklet.moved` / `worklet.closed`) | 只追加 | `services/work/trace.py` |
| `rounds` | agent 工作单元的一条 round | 只追加,按 (`worklet_id`, `round_id`) 去重 | `services/work/rounds.py` |

共同约定:

- **id 是小写十六进制串**:trace id 32 位(16 字节),span id 16 位(8 字节),都由身份算出来(§2),不随机。
- **时间是 Unix 纳秒**,`INTEGER`(64 位,到 2262 年都够);对外导出时写成十进制字符串。`rounds.timestamp` 例外,存平台原样的文本(§4)。
- **`attributes` / `links` 是 OTLP 的 JSON**,存成文本:`attributes` 是 KeyValue 列表 `[{"key": …, "value": {"stringValue" | "intValue"(十进制串)| "boolValue" | "doubleValue": …}}]`,值为空的键不写;`links` 是 `[{"traceId", "spanId", "attributes": []}]`。
- **提升列**:要拿来查的几个值从属性里提出来另存一列(`user_id`、`end_user_id`、`worklet_id`、`column_number`),JSON 里照样留着;对外只用 JSON。`work_id` 是存储用的列,不一定在属性里(`agent.turn` 段和点的属性里没有)。
- **没有外键**:`work_id` / `worklet_id` 指向 `works.db`,跨库约束不了;工作单元关掉后 `worklets` 里那一行删了,轨迹里的 id 照样留着——经过比现在活得久。
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
  name                 TEXT,
  kind                 INTEGER,
  start_time_unix_nano INTEGER,
  end_time_unix_nano   INTEGER,
  status_code          INTEGER,
  attributes           TEXT,      -- OTLP KeyValue 列表(JSON)
  links                TEXT,      -- OTLP Link 列表(JSON)
  first_round_id       TEXT
);
CREATE INDEX idx_spans_trace_id    ON spans(trace_id);
CREATE INDEX idx_spans_work_id     ON spans(work_id);
CREATE INDEX idx_spans_worklet_id  ON spans(worklet_id);
CREATE INDEX idx_spans_user_id     ON spans(user_id);
CREATE INDEX idx_spans_end_user_id ON spans(end_user_id);
```

| 列 | 空 | OTLP | 什么时候写 | 说明 |
|---|---|---|---|---|
| `span_id` | 否 | `spanId` | 开 | 由身份算:`work` = `sha256("memorytalk/span/work/<work id>/<第几段>")`,`worklet` = `…/span/worklet/<worklet id>/<第几段>`,`agent.turn` = `…/span/turn/<worklet id>/<第一条 round 的 id>`,都取前 16 位。「第几段」= 这个 work / 工作单元已有几段同名的段,从 0 起 |
| `trace_id` | 否 | `traceId` | 开 | `sha256("memorytalk/trace/<根 work id>")` 前 32 位:一棵 work 树一条 trace |
| `parent_span_id` | 是 | `parentSpanId` | 开 | `work`:父 work 最新的一段 `work` 段,根 work 为空;`worklet`:所在 work 最新的一段 `work` 段;`agent.turn`:所在工作单元最新的一段 `worklet` 段 |
| `work_id` | 否 | —(`work` / `worklet` 段另有属性 `memorytalk.work.id`) | 开 | 属于哪个 work |
| `worklet_id` | 是 | 属性 `memorytalk.worklet.id` | 开 | `worklet` / `agent.turn` 段有,`work` 段为空 |
| `user_id` | 是 | 属性 `user.id` | 开 | 开它的人(建 / 重新打开 work、打开 / 重入工作单元的人);没带身份为空;`agent.turn` 永远为空(轮次是 agent 的) |
| `end_user_id` | 是 | 属性 `memorytalk.end.user.id` | 结束 | 结束它的人;开着、`gone`、重新打开时补记的归档(不知道是谁)、`agent.turn` 都为空 |
| `name` | 否 | `name` | 开 | `work` / `worklet` / `agent.turn` |
| `kind` | 否 | `kind` | 开 | 恒为 1(INTERNAL) |
| `start_time_unix_nano` | 否 | `startTimeUnixNano` | 开 | 动作发生的时刻;`agent.turn` 取它第一条 round 的时刻 |
| `end_time_unix_nano` | 是 | `endTimeUnixNano` | 结束 | **空 = 还开着**,不另存「开着」的状态;读的时候开着的段不出 `endTimeUnixNano`,另加属性 `memorytalk.open = true` |
| `status_code` | 否 | `status.code` | 开 / 结束 | 0 = Unset(开着;`gone` 结束的段和跟着它结束的轮次也保持 0);1 = OK(正常结束);2(Error)不用 |
| `attributes` | 否 | `attributes` | 开;结束时合并 | 开时写开的属性 + `user.id`;结束时把结束的属性(`memorytalk.end.reason`、`memorytalk.end.user.id`,`worklet` 段另有 `memorytalk.end.column.id` / `.alias`)并进来,同名的键以结束时为准。各段有哪些键见 [work.md 的 Trace](work.md#trace) |
| `links` | 否 | `links` | 开 | 只有重新打开的 `work` 段有一条,指向上一段;其余是 `[]` |
| `first_round_id` | 是 | 属性 `memorytalk.round.first` | 开 | 只有 `agent.turn` 有:这一轮第一条 round 的 id,轮次的身份 |

按 `name` 看哪些列有值:

| `name` | `worklet_id` | `parent_span_id` | `user_id` / `end_user_id` | `first_round_id` | `links` |
|---|---|---|---|---|---|
| `work` | 空 | 父 work 的 `work` 段(根为空) | 有 | 空 | 重新打开的那段有 |
| `worklet` | 有 | 所在 work 的 `work` 段 | 有 | 空 | `[]` |
| `agent.turn` | 有 | 所在工作单元的 `worklet` 段 | 都空 | 有 | `[]` |

**怎么改**:

- **插**:开段就是插一行,终点为空、status 0。id 由身份算,同一段开两次会撞主键——重复开是错,不会悄悄多一行。
- **结束**:在事务里先看终点是不是空,空才补上终点、status、`end_user_id`、合并属性;已经有终点的不再动(两处同时结束同一段,只算先到的)。所以 **`work` / `worklet` 段结束后不再变**。
- **`agent.turn` 是例外**:每次同步进新 round 都整体重切一遍,按 `first_round_id` 幂等写——没有就插,终点 / status / 属性变了就原地改(属性整份换掉)。结束了的轮次不会重新打开,但后来又同步进来、还属于它的 round 会把终点往后挪。
- **不变式**(由写入路径保证,表上没有约束):一个 work 同时最多一段 `work` 段开着;一个工作单元同时最多一段 `worklet` 段开着;一个工作单元的轮次 `first_round_id` 互不相同。

---

## 3. points:点

```sql
CREATE TABLE points (
  seq            INTEGER PRIMARY KEY AUTOINCREMENT,
  trace_id       TEXT,
  span_id        TEXT,
  work_id        TEXT,
  worklet_id     TEXT,
  column_number  INTEGER,
  user_id        TEXT,
  event_name     TEXT,
  time_unix_nano INTEGER,
  attributes     TEXT       -- OTLP KeyValue 列表(JSON)
);
CREATE INDEX idx_points_span_id    ON points(span_id);
CREATE INDEX idx_points_work_id    ON points(work_id);
CREATE INDEX idx_points_user_id    ON points(user_id);
CREATE INDEX idx_points_event_name ON points(event_name);
```

| 列 | 空 | OTLP | 说明 |
|---|---|---|---|
| `seq` | 否 | — | 写入的先后,自增不复用;读按它排 |
| `trace_id` | 否 | `traceId` | 所在 work 树的 trace |
| `span_id` | 是 | `spanId` | 挂在哪一段:`work.renamed` / `column.*` 挂 work 最新的 `work` 段,`worklet.moved` / `worklet.closed` 挂这个工作单元最新的 `worklet` 段;那一段不存在时为空 |
| `work_id` | 否 | — | 属于哪个 work |
| `worklet_id` | 是 | 属性 `memorytalk.worklet.id` | `worklet.*` 的点有 |
| `column_number` | 是 | 属性 `memorytalk.column.id` 的编号(`c3` → 3) | 这个点关于哪一列:`column.*` 是那一列,`worklet.moved` 是挪去的那列,`worklet.closed` 是关的时候所在的列;`work.renamed` 为空 |
| `user_id` | 是 | 属性 `user.id` | 谁做的;没带身份为空 |
| `event_name` | 否 | `eventName` | `work.renamed` / `column.added` / `column.renamed` / `column.removed` / `worklet.moved` / `worklet.closed`;各自的属性见 [work.md 的 Trace](work.md#trace) |
| `time_unix_nano` | 否 | `timeUnixNano`(`observedTimeUnixNano` 读的时候填同一个值) | 写的那一刻(服务端时钟) |
| `attributes` | 否 | `attributes` | 含 `user.id` |

**只追加**:插了就不改、不删。

---

## 4. rounds:agent 的 round

```sql
CREATE TABLE rounds (
  seq        INTEGER PRIMARY KEY AUTOINCREMENT,
  work_id    TEXT,
  worklet_id TEXT,
  round_id   TEXT,
  timestamp  TEXT,
  role       TEXT,
  text       TEXT
);
CREATE INDEX idx_rounds_worklet_id ON rounds(worklet_id);
```

| 列 | 空 | 说明 |
|---|---|---|
| `seq` | 否 | 追加的先后,自增不复用。同步按会话记录的顺序追加,所以**同一个工作单元里 `seq` 的顺序就是对话的顺序**;读按它排 |
| `work_id` | 否 | 属于哪个 work(只作记录,不查) |
| `worklet_id` | 否 | 属于哪个工作单元 |
| `round_id` | 否 | 平台自己的消息 id:Claude Code 是记录里的 `uuid`;Codex 是 `<rollout 文件名>:<行号>`;Kimi 的人的输入是 `<session 目录名>:<行号>`、模型输出是事件的 `uuid`、工具结果是 `toolCallId`。和 `worklet_id` 一起是去重键 |
| `timestamp` | 是 | 平台原样的文本,格式不统一(Claude Code / Codex 是 ISO 串,Kimi 是数字);**不拿它排序**。切轮次时才换算成 Unix 纳秒(`services/work/turns.py`) |
| `role` | 否 | `human` / `assistant` / `tool` / `system` |
| `text` | 否 | 扁平化的文本:工具调用 `[Name] args`、结果 `[result] …`、思考 `[thinking] …` |

**只追加**。去重在应用里做:同步时在进程内的锁里先读出这个工作单元已有的全部 `round_id`,跳过见过的,其余在一个事务里追加——**表上没有唯一约束**(§6)。

`agent.turn` 段只引用 round(`first_round_id` 和属性 `memorytalk.round.first` / `.last` / `.count`),正文只在这张表里;round 不进 OTLP 导出。

---

## 5. 读写纪律和查询

- **单写者**:服务进程是唯一写这个库的;WAL 模式,读不挡写。
- **先 works.db,后 worktrace.db**:一个动作先在 `works.db` 里做完,再写轨迹;轨迹写失败只记日志,不回滚 work(两个库之间没有原子提交)。
- **「查一下再写」在事务里**:第几段、开没开着、轮次重切、round 去重,都包在 `worktrace.db` 的一个事务里;要读 `works.db` 的(trace id 要走到根)在事务外先算好。两把锁只按「worktrace → works」或单独一把的顺序拿。

| 查询 | 谁用 | 条件 / 顺序 | 走的索引 |
|---|---|---|---|
| 一个 work 的 `work` 段 | 算第几段、找最新的 `work` 段 | `work_id = ? AND name = 'work'`,按 (`start_time_unix_nano`, `span_id`) | `idx_spans_work_id` |
| 一个 work 开着的段 | 归档、重新打开 | `work_id = ? AND name = ? AND end_time_unix_nano IS NULL` | `idx_spans_work_id` |
| 一个工作单元的段 / 轮次 | 找最新的 `worklet` 段、重入、重切轮次 | `worklet_id = ? AND name = 'worklet' / 'agent.turn'` | `idx_spans_worklet_id` |
| 一组 work 的段和点 | `GET /works/{id}/trace`(`subtree` 时是全部子孙 work) | `work_id IN (…)`;段按开始时间,点按 `seq` | `idx_spans_work_id`、`idx_points_work_id` |
| 某人出现过的 work | 用户页「动过哪些 work」 | `spans.user_id = ?`、`spans.end_user_id = ?`、`points.user_id = ?` | 三个 `user_id` 索引 |
| 一个工作单元的全部 round | `GET …/rounds`、同步去重、重切轮次 | `worklet_id = ?`,按 `seq` | `idx_rounds_worklet_id` |

现在**没有查询用到**的索引:`idx_spans_trace_id`、`idx_points_span_id`、`idx_points_event_name`——留给按整棵树查、瀑布图按段取点、时间线按类型筛(都还没做)。

---

## 6. 已知问题和待改(未实施)

前四条是现状的毛病;后几条是 work server 改成「边上推、中心收」之后表上要加的,推的设计稿写的时候以这里为起点一起定。

1. **`rounds` 没有唯一约束**。去重靠进程内的锁 + 每次全量读出已有的 `round_id`:多一个写者(比如边上的节点直接推)就守不住。要加 `UNIQUE(worklet_id, round_id)`,写改成 `INSERT … ON CONFLICT DO NOTHING`——这也是推的模式「至少一次投递、接收口幂等」的前提。
2. **每次同步都把这个工作单元的 round 全读一遍**(去重),有新 round 时再全读一遍(重切轮次),`GET …/rounds` 再读一次,会话越长越慢。改成按游标读:`WHERE worklet_id = ? AND seq > ?`,换成 (`worklet_id`, `seq`) 的复合索引;轮次只从变化的地方往后切。
3. **时间没在写入时统一**。`rounds.timestamp` 存原样文本,切轮次时才猜格式;Kimi 的数字其实是**毫秒**,现在被当成秒,换算出来是几万年后。改成写入时由懂格式的一方(adapter / 边上的上报者)换算好,另存一列 `time_unix_nano INTEGER`,原文留着备查。
4. **`agent.turn` 结束后还会被改**(终点往后挪、属性整份换),和「段结束了就不再变、导出时整条写出」的约定不一致。轮次改用平台记录里明确的收尾标记来结束之后(Claude Code 的 `stop_reason`、Codex 的 `task_complete` / `turn_aborted`、Kimi 的 `turn.ended` / `turn.cancel`),可以做到结束即定稿;同时加 `memorytalk.end.reason`(正常结束 / 打断 / 现场没了)。
5. **推的游标**:中心是「收到哪了」的权威,边上重连时来问。要一张表记每个工作单元每份来源收到的位置,形如 `ingest_cursors(worklet_id, source, position, updated_at)`,`source` = 哪一份会话记录(会话 id 或文件),`position` = 读到的偏移或最后一条的序号。放在这个库里,因为它跟着 `rounds` 走。
6. **round 来自哪一份会话**:一个工作单元一生可能对应几份会话记录(Claude Code 里 `/clear` 就换一份),`rounds` 要加 `source`,对得上游标、也说得清是哪次会话。
7. **新的点**:`worklet.state`(空闲 / 忙 / 等确认 / 不在了)、`worklet.input`(谁送了什么,不存原文)——见 [designs work-server-io.md](../../designs/v5/work-server-io.md)。`points` 的列够用,不用改表;按工作单元查状态时再给 `worklet_id` 加索引。
8. **只增不减**:三张表没有清理路径,`worktrace.db` 会一直长;按时间切库还是导出后删,和 [work-store.md §8](../../designs/v5/work-store.md) 一起定。
