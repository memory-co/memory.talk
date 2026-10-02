# work-trace —— 把 events 换成 trace:OTel 格式,分点和段,一张图从可观测走到甘特(v5 设计)

> **状态:部分实施。** 已经有了:落盘(`worktrace.db`)、`work` / `worklet` 两种段和 §2 的动作点(`plan.changed` 除外)、`GET /works/{id}/trace`(§6)、右侧「动态」列表(§6 的第 3 种视图)。代码在 `services/work/trace.py`。
>
> **agent 那一层还没做**:节点、会话 / 轮次 / 工具段、消息点和写入口(`POST …/trace`)都按 [work-node.md](work-node.md) 来;现在的代码还是中心去拉、单独存一份 round,实施时去掉(§9)。另外还没做的:瀑布图 / 甘特图(§6 的 1、2)、计划(§7)、往外导出和直推(§8 的 2、3)。
>
> 本篇把 work 的时间线从「一串事件」换成 **trace**:有起止的东西记成**段(span)**,瞬间发生的事记成**点(event)**,落盘格式就是 OpenTelemetry 的 **OTLP/JSON**,一行一条。这样做有三个目的:
>
> 1. 这份数据不用转换,就能交给 Collector、Jaeger、Tempo 这类可观测后端;
> 2. memory.talk 自己能画出类似 Chrome DevTools Network 那样的瀑布图;
> 3. 同一张瀑布图拉到「天」的尺度就是甘特图,可观测和项目管理用的是同一份数据。
>
> **落盘位置已改**:轨迹存在 `worktrace.db`(见 [work-store.md §5](work-store.md)),表的列和 OTel 字段一对一,逐列的设计见 [structure worktrace.md](../../structure/v5/worktrace.md)。§3 的 OTLP/JSON 是**对外的格式和字段规范**:接口返回、导出文件、OTLP 推送都用它;库里不存信封本身。
>
> 本篇已经取代 [work-events.md](work-events.md) 的存储部分(动作表、列标记、`by` 这些规则保留)。

相关:
- 现在的事件:一个动作一个请求,每条带列标记和 `by`: [work-events.md](work-events.md)
- 轨迹存在哪:`worktrace.db` 逐列的表设计 [structure worktrace.md](../../structure/v5/worktrace.md);为什么单独一个库 [work-store.md §5](work-store.md)
- work 树、worklet 的身份: [work.md](work.md) / [worklet.md](worklet.md)
- agent 的记录谁往上推(节点读会话记录、收 hooks,推给中心): [work-node.md](work-node.md);每个 server 的 input / output 口子: [work-server-io.md](work-server-io.md)
- OTLP/JSON 编码: <https://opentelemetry.io/docs/specs/otlp/#json-protobuf-encoding>;Collector 的 `otlpjsonfile` receiver / `file` exporter 读写的就是这种一行一条的格式
- OTel GenAI 语义约定(会话、工具调用、token 的属性名): <https://opentelemetry.io/docs/specs/semconv/gen-ai/>

---

## 1. 为什么:events 只有点,可是 work 里的东西大多有长度

原来 `events.jsonl` 里每条都是一个时刻:`worklet.attached` 一条、`worklet.detached` 另一条。可是「这个终端从 10:02 开到 15:40」本来就是**一段时间**。拆成两个点以后:

- **想画条要自己配对**。拿 attached 和 detached 按 worklet id 配成一对,中间断了(服务重启、现场自己退出了)就配不上,只能靠猜。
- **没有层级**。子 work、work 里的终端、终端里 agent 的一轮,本来一层套一层;事件是平的,每条只能靠 `work_id` 挂到某个 work 下面。
- **外面接不了**。自造的 `{ts, type, data}` 格式,可观测那边没有一个工具认识;要接就得写一层转换。
- **跟项目管理是两套东西**。甘特图要的是「每件事从哪天到哪天、谁套着谁、谁卡着谁」,和 trace 瀑布图的结构一模一样,可现在两边的数据各记各的。

trace 模型本来就有这些:span 有起点和终点;父子关系决定层级;span 之间可以 link;一个时刻用 event 记。OTel 把这套东西标准化了,我们直接用。

## 2. 点和段:哪些是 span,哪些是 event

**段(span)= 有起止的东西。** 一个 span 有开始、有结束,可以套子 span。

| span | 起 | 止 | 父 | 谁写 |
|---|---|---|---|---|
| `work` | 建 work(`created`);重新打开(新的一段) | 归档(`archived`) | 父 work 最新的一段 `work` span;根 work 没有父 | 中心 |
| `worklet` | 打开工作单元(`attached`);重入时没有开着的段就开新的一段;work 重新打开时现场还活着的(网页的)也开新的一段 | 关掉(`detached`)、所在 work 归档(`archived`),或现场没了(`gone`,§5) | 所在 work 最新的一段 `work` span | 中心;`gone` 由节点报 |
| `agent.session` | agent 开始一个会话:新开、`/resume` 接回、`/clear` 之后的新会话(Claude Code 的 `SessionStart`) | 被下一个会话接替,或 worklet 段结束(原因跟着它) | 所在工作单元最新的一段 `worklet` span | 节点 |
| `agent.turn` | 人发出的一条输入 | agent 收完这一轮(Claude Code 的 `Stop` / `stop_reason = end_turn`、Codex 的 `task_complete`、Kimi 的 `turn.ended`);被打断也结束(Esc、`turn_aborted`、`turn.cancel`);会话段先结束了就跟着结束 | 所在会话段 | 节点 |
| `agent.tool` | agent 发起一次工具调用 | 拿到这次调用的结果(按调用 id 配对);轮次先结束了就跟着结束 | 所在轮次段 | 节点 |

**点(event)= 一个时刻发生的事。** 点没有长度,但它总挂在某个 span 上,意思是「在这段时间里的某一刻发生了这件事」。点分两类。

**动作点**:中心写,人做动作的那一刻。

| 点 `event.name` | 挂在 | 属性(除 `user.id` 外) |
|---|---|---|
| `work.renamed` | work span | `memorytalk.work.goal`、`memorytalk.from` |
| `column.added` / `column.renamed` / `column.removed` | work span | `memorytalk.column.id`、`memorytalk.column.alias`(`renamed` 另有 `memorytalk.from`;别名真变了才记) |
| `worklet.moved` | 这个工作单元最新的一段 worklet span | `memorytalk.worklet.id`,`memorytalk.column.id` / `.alias` 和 `memorytalk.index`(去哪),`memorytalk.from.column.id` / `.alias` 和 `memorytalk.from.index`(从哪);位置真变了才记 |
| `worklet.closed` | 这个工作单元最新的一段 worklet span | `memorytalk.worklet.id`、`memorytalk.column.id` / `.alias`(关的时候在哪一列);关掉时它已经没有开着的段(现场没了 / 归档过、重新打开后没重入)才记,段不再动 |
| `worklet.input` | 这个工作单元最新的一段 worklet span | `memorytalk.input.id` / `.kind` / `.length` / `.sha256`;**不存原文**([work-server-io.md §4.3](work-server-io.md),还没做) |
| `plan.changed` | work span | `memorytalk.plan.start` / `memorytalk.plan.due`(§7,还没做) |

**agent 点**:节点写,来自会话记录和 hooks。正文放在 log record 的 `body` 里。

| 点 `event.name` | 挂在 | `body` | 属性 |
|---|---|---|---|
| `agent.message` | 所在轮次段;第一条人的输入之前的(系统提示之类)挂会话段 | 这条消息的正文(扁平文本) | `memorytalk.message.role`(`user` / `assistant` / `system`)、`memorytalk.message.kind`(`text` / `thinking`)、`log.record.uid` |
| `agent.tool.input` | 那次调用的工具段 | 调用参数(JSON 文本) | `gen_ai.tool.name`、`gen_ai.tool.call.id`、`log.record.uid` |
| `agent.tool.output` | 那次调用的工具段 | 结果正文 | `gen_ai.tool.call.id`、`memorytalk.tool.error`(结果标了出错时为 `true`)、`log.record.uid` |
| `agent.state` | 会话段 | — | `memorytalk.state`(`idle` / `busy` / `blocked`,[work-server-io.md §5](work-server-io.md)) |

- **正文只在点的 `body` 里**,段上只放结构和计数,不放大块内容。人的输入是它那一轮的第一个点。
- **子 agent**(Claude Code 用 Task 工具派出去的):它的消息和工具调用挂在派它的那个工具段下面——子 agent 的一轮就是那个工具段下的一段 `agent.turn`。

原来 `events` 里的每一种都有着落,原来的 round 也一样:

| 原来的 | trace 里 |
|---|---|
| `created` | `work` span 的开始 |
| `status`(→ `archived`)/ `frozen` | `work` span 的结束。冻结和归档是同一个时刻,一个 span 结束就够了,不再单记 |
| `status`(`archived` → `running`,重新打开) | 开一个新的 `work` span:同一个 work id,新的 span id,用 link 指向上一段(§4)。甘特上同一行出现两段 |
| `worklet.attached` / `worklet.detached` | `worklet` span 的开始 / 结束;关的时候段已经结束了,记一个 `worklet.closed` 点 |
| `worklet.moved`、`column.*` | 点 |
| (改目标,原来不记) | `work.renamed` 点 |
| round(原来在 `rounds` 表里) | 一条 `agent.message` / `agent.tool.input` / `agent.tool.output` 点;一轮是一段 `agent.turn` |

收起 / 展开仍然不记(同 work-events.md §2)。收件箱不进 trace:收件箱是别的 work 打过来的消息,不是这个 work 自己的经过。

## 3. 格式:OTLP/JSON(落盘在 worktrace.db)

> 下面讲的「一行一个信封」是**导出格式**(`trace.jsonl`,导出还没做,§8)。`GET /trace` 用的是同一套编码,只是把这个 work 的段装进**一个** `resourceSpans`、点装进**一个** `resourceLogs`,开着的段也在里面(§6)。真相来源是 `worktrace.db`,见本节末尾。

**一行一个完整的 OTLP 信封**,内容是 Collector `file` exporter 写出来的那种。行分两种,看顶层 key 就能区分:

- **段** = `{"resourceSpans": [...]}`,里面装**一个已经结束的** span;
- **点** = `{"resourceLogs": [...]}`,里面装**一条** log record,带 `eventName`,再用 `traceId` / `spanId` 挂到所属的 span 上。

点用 log record 表示,不塞进 span 的 `events[]`,原因有两个。第一,span 在结束时才整条写出(见下),而点要在发生的当下就落盘;一个 work span 可能开几个月,把点攒在它的 `events[]` 里,等于这几个月都不落盘。第二,OTel 已经把「有名字的事件」统一到 Logs 信号上(LogRecord 的 `event_name` 字段),Span Events 正在往这个方向收拢;按新的做法来,后端那边也是按 trace / span id 关联起来显示。

段的一行(换行和缩进只为好读,实际是一行):

```json
{"resourceSpans":[{"resource":{"attributes":[
    {"key":"service.name","value":{"stringValue":"memory.talk"}}]},
  "scopeSpans":[{"scope":{"name":"memorytalk.work","version":"5"},
    "spans":[{
      "traceId":"4bf92f3577b34da6a3ce929d0e0e4736",
      "spanId":"00f067aa0ba902b7",
      "parentSpanId":"a3ce929d0e0e4736",
      "name":"worklet",
      "kind":1,
      "startTimeUnixNano":"1790590931000000000",
      "endTimeUnixNano":"1790611211000000000",
      "attributes":[
        {"key":"memorytalk.work.id","value":{"stringValue":"work_202609291002…"}},
        {"key":"memorytalk.worklet.id","value":{"stringValue":"work_202609291002…-w4"}},
        {"key":"memorytalk.worklet.uri","value":{"stringValue":"bash:///ws"}},
        {"key":"memorytalk.worklet.scheme","value":{"stringValue":"bash"}},
        {"key":"memorytalk.worklet.server","value":{"stringValue":"bash"}},
        {"key":"memorytalk.column.id","value":{"stringValue":"c3"}},
        {"key":"memorytalk.column.alias","value":{"stringValue":"测试"}},
        {"key":"user.id","value":{"stringValue":"alice"}},
        {"key":"memorytalk.end.reason","value":{"stringValue":"detached"}},
        {"key":"memorytalk.end.column.id","value":{"stringValue":"c1"}},
        {"key":"memorytalk.end.column.alias","value":{"stringValue":""}},
        {"key":"memorytalk.end.user.id","value":{"stringValue":"bob"}}],
      "links":[],
      "status":{"code":1}}]}]}]}
```

点的一行:

```json
{"resourceLogs":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"memory.talk"}}]},
  "scopeLogs":[{"scope":{"name":"memorytalk.work","version":"5"},
    "logRecords":[{
      "timeUnixNano":"1790598000000000000",
      "observedTimeUnixNano":"1790598000000000000",
      "eventName":"worklet.moved",
      "traceId":"4bf92f3577b34da6a3ce929d0e0e4736",
      "spanId":"00f067aa0ba902b7",
      "attributes":[
        {"key":"user.id","value":{"stringValue":"bob"}},
        {"key":"memorytalk.worklet.id","value":{"stringValue":"work_202609291002…-w4"}},
        {"key":"memorytalk.column.id","value":{"stringValue":"c1"}},
        {"key":"memorytalk.column.alias","value":{"stringValue":""}},
        {"key":"memorytalk.index","value":{"intValue":"1"}},
        {"key":"memorytalk.from.column.id","value":{"stringValue":"c3"}},
        {"key":"memorytalk.from.column.alias","value":{"stringValue":"测试"}},
        {"key":"memorytalk.from.index","value":{"intValue":"0"}}]}]}]}]}
```

agent 的点多一个 `body`;`timeUnixNano` 是 agent 记录里的时刻,`observedTimeUnixNano` 是中心收到的时刻,两个不一样:

```json
{"resourceLogs":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"memory.talk"}}]},
  "scopeLogs":[{"scope":{"name":"memorytalk.work","version":"5"},
    "logRecords":[{
      "timeUnixNano":"1790598012345000000",
      "observedTimeUnixNano":"1790598013002000000",
      "eventName":"agent.message",
      "traceId":"4bf92f3577b34da6a3ce929d0e0e4736",
      "spanId":"9c1d7e0b5a2f4c33",
      "body":{"stringValue":"把配置改成环境变量"},
      "attributes":[
        {"key":"log.record.uid","value":{"stringValue":"work_202609291002…-w4:8b1e…"}},
        {"key":"memorytalk.message.role","value":{"stringValue":"user"}},
        {"key":"memorytalk.message.kind","value":{"stringValue":"text"}}]}]}]}]}
```

编码规则都按 OTLP/JSON 规范来:`traceId` / `spanId` 用十六进制字符串(不用 base64);64 位整数(时间戳、`intValue`)写成十进制字符串;`kind` 和 `status.code` 写成整数;`body` 是 AnyValue,正文写成 `stringValue`;字段名是 lowerCamelCase。属性分两类:

- **通用语义约定里有的,用标准名**:`service.name`、`user.id`、`log.record.uid`,还有 GenAI 的 `gen_ai.*`(§4);
- **我们自己的,一律放在 `memorytalk.*` 命名空间下**。

**段在结束时才写,写的时候是整条。** OTLP 里的 span 是一条不可变的完整记录,没有「先写开头、再补结尾」这回事。所以:

- 导出的 `trace.jsonl` 只收**已经结束**的 span 和所有的点,真正做到只追加,Collector 的 `otlpjsonfile` receiver 能直接读;
- **还开着的 span** 不出现在导出里(OTLP 没有「开着的 span」),只在 memory.talk 自己的图里画出来。

**真相来源是 `worktrace.db`**(为什么单独一个库见 [work-store.md §5](work-store.md),逐列见 [structure worktrace.md](../../structure/v5/worktrace.md)):

| 表 | 装什么 |
|---|---|
| `spans` | 一行一个段,列和 OTLP span 一对一;**`end_time_unix_nano` 为空 = 还开着**,结束时在同一行补上终点。开着的段不用再另存一份状态。另存它最后一次改动的变更序号 `seq` |
| `points` | 一行一个点,列和 OTLP log record 一对一(含 `body`、`observed_time_unix_nano`),只追加;节点推来的点带 `uid`(= `log.record.uid`),按它去重。`seq` 是它写入时的变更序号 |
| `trace_cursors` | 每个工作单元每份来源推到哪了:随 `POST …/trace` 一起写,节点重连时用 `GET …/trace?fields=cursors` 读回([work-node.md §6](work-node.md)),中心说了算 |

每行带 `work_id`(属于哪个 work)和 `trace_id`(属于哪棵树):一个 work 的轨迹按 `work_id` 查,整棵树按 `trace_id` 查。

**一个变更序号管两张表。** 段的每次开、改(结束、合并属性),点的每次写入,都在同一个事务里取下一个 `seq`;段记它最后一次改动的序号。读的时候 `after=<seq>` 就接得住所有变化——新的消息、新开的轮次、刚结束的轮次、状态的变化——这是读 output、刷新界面用的**唯一的游标**(§6)。

**正文会让 `points` 大很多。** 列表和图的查询不取 `body`(§6);真拖慢了,再把 agent 点拆到单独的表或库(§10)。

## 4. id:一棵 work 树是一条 trace

- **trace id = 根 work**:`traceId = sha256("memorytalk/trace/" + 根 work id)` 的前 16 字节。一棵 work 树从根到叶都在同一条 trace 里,所以不管在瀑布图还是甘特图上,一次就能看到整件事。子 work 不单独开 trace。
- **span id 由身份算出来,算的一方手里的东西就够,不用查**(都取 sha256 的前 8 字节):
  - `work`:`"memorytalk/span/work/" + work id + "/" + 第几段`(第几段 = 这个 work 已经有几段 work 段,第一段是 0;见 §2 的「重新打开」),中心算;
  - `worklet`:同理,用 worklet id,中心算;
  - `agent.session`:`"memorytalk/span/session/" + worklet id + "/" + 会话 id + "/" + 这一段第一条记录的 uid`——同一个会话 `/resume` 回来是新的一段,节点算;
  - `agent.turn`:`"memorytalk/span/turn/" + worklet id + "/" + 这一轮人那条输入的 uid`,节点算;
  - `agent.tool`:`"memorytalk/span/tool/" + worklet id + "/" + 调用 id`(Claude Code 的 `tool_use.id`、Codex 的 `call_id`、Kimi 的 `toolCallId`),节点算。

  算得出来就不用查:子 work 知道自己的父 span id,打开工作单元时也知道它该挂在哪个 work span 下面;节点不用问中心就能算出它推的每一段的 id。同一段推两次还是同一个 id,中心按 id 幂等收([work-node.md §6](work-node.md))。
- **`log.record.uid` = 点的身份**:节点推的点都带,`<worklet id>:<来源里的消息 id>`;一条记录里有几块内容(一条助手消息里几段文字、几个工具调用)时再加 `:<第几块>`。来源里的消息 id 是 Claude Code 的 `uuid`、Codex 的 `<rollout 文件名>:<行号>`、Kimi 的事件 `uuid`。中心按它去重;认知层引用某一条消息(issue 的出处、card 的出处)也用它。中心自己写的动作点没有 uid,只追加。
- **link = 依赖**:span 的 `links[]` 用来表示「这件事等着那件事」(§7 的依赖),以及「重新打开的这一段接的是上一段」(work 重新打开、会话 `/resume`)。link 写在 `spans` 表那一行的 `links` 列里(OTLP 的 `{traceId, spanId, attributes}`),导出时随整条一起写出。现在只有 work 重新打开时写,开段那一刻一起写;依赖的 link 等 §7。
- **不能挪树**:trace id 取决于根,所以 work 不能换父(现在本来也不能:`PATCH /works/{id}` 只改目标和状态)。

**agent 那几层对上 OTel GenAI 语义约定。** 会话段带 `gen_ai.conversation.id`(agent 自己的会话 id);轮次段带 `gen_ai.operation.name = invoke_agent` 和这一轮的 token 数(`gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens`:Claude Code 每条助手消息带 `usage`,Codex 有 `token_count`,Kimi 有 `usage.record`,节点加总);工具段带 `gen_ai.operation.name = execute_tool`、`gen_ai.tool.name`、`gen_ai.tool.call.id`;三层都带 `gen_ai.system`(`anthropic` / `openai` / `moonshot`)。这样可观测那边现成的 LLM 看板能直接用。GenAI 规范还在变,具体用哪一版的名字,实施时对一遍。

## 5. 写:谁在什么时候开段、关段、打点

**两个写的人:**

- **中心**:人做的动作——`work` / `worklet` 段、动作点。
- **节点**:agent 的记录——`agent.*` 段和点、`agent.state`、worklet 段的 `gone` 结束。经 **`POST /api/works/{id}/trace`** 推上来:和 `GET` 同一个路径、同一个 OTLP/JSON 形状,一次请求一个事务([work-node.md §6](work-node.md));**中心不解析任何 agent 的格式,也不切轮次**。

**一条写路径。** 两边进的是同一个写入函数:收 OTLP/JSON 的段和点(段按 `spanId`:没有就插,开着的收到终点就补上、收到开着的就合并属性,结束了就跳过;点按 `log.record.uid`,有了就跳过),落成下面四个动作,每个真写了的都取下一个变更序号(§3)。中心自己的动作只是不经过 HTTP。

```
start(work_id, name, span_id, parent_span_id, attributes, *, user, worklet_id, links, at)
    → spans 表插一行:终点为空,status Unset;trace id 由根 work 算;同一个 span id 已经有了就跳过
merge(span_id, attributes)
    → 开着的段合并属性,同名的以新的为准;结束了的不动
end(span_id, attributes, *, status=OK, user, at)
    → 同一行补上终点、status、end_user_id,结束时的属性并进 attributes;已经结束的不再动(两处同时结束,只算先到的)
point(work_id, span_id, event_name, attributes, *, user, worklet_id, column_number, body, uid, at)
    → points 表追加一行;带 uid 的已经有了就跳过
```

往外导出(§8)还没做,所以现在只写库。「查一下再写」的几处(第几段、还开着没有)包在 `worktrace.db` 的一个事务里。

写入顺序沿用 [work-store.md §6](work-store.md):先改快照(登记、列和位置),再动 trace;trace 写失败只记日志,不让动作失败,也不回滚快照。带身份的都写 `user.id`(同时进 `spans.user_id` / `points.user_id` 列),取登录态里的人;没有人的就不写(`agent.*`、`gone`)。结束一个 span 的时候,结束它的人记在 `memorytalk.end.user.id`(和 `spans.end_user_id` 列;是开它的同一个人也记),怎么结束的记在 `memorytalk.end.reason`(`detached` / `archived` / `gone`;agent 那几层另有 `completed` / `cancelled` / `replaced`);worklet 段另记结束那一刻在哪一列(`memorytalk.end.column.id` / `.alias`)。worklet 段开的时候带 `memorytalk.worklet.uri`(原样的 uri)/ `.scheme` / `.server` 和当时的列。

各种段什么时候开、什么时候结束:

- **`work`**(中心):建 work 时开;归档时先把这个 work 开着的 worklet 段都结束(reason `archived`),再结束 work 段(结束的是这个 work 所有还开着的 work 段,不只是最新的一段);重新打开是新的一段,link 指向上一段,带 `memorytalk.work.reopened = true`。一个 work 同时只有一段 work 段开着:归档要先让节点把记录推完、逐个销毁现场,做完才结束段,这中间别人重新打开、打开或重入工作单元都得等它做完(同一个 work 的这几个动作在服务里排队,[work-store.md §6](work-store.md));重新打开时上一段还开着(那次归档的轨迹没写进去),先按归档补上终点(reason `archived`,终点取 `works.archived_at`,不记人),上一段里还开着的 worklet 段一样。
- **`worklet`**(中心):打开工作单元时开(登记写进 `works.db` 之后);关掉时结束(`detached`,status OK,登记删掉之后);归档时结束(`archived`,status OK);重入时这个工作单元没有开着的段才开新的一段(父是 work 最新的一段;work 已归档不能重入,409——不然结束了的 work 段下面会开着一段 worklet 段,重新打开时又被补成长度为 0 的 `archived`);work 重新打开时,现场还活着的工作单元(网页的一直活着,没人会去重连)同样接着开新的一段,开的人记重新打开的人。关掉时已经没有开着的段(现场没了、归档过又重新打开还没重入),段不再动,在它最新的一段上打一个 `worklet.closed` 点记下谁在哪一列关的。**关掉和归档之前,先让节点把这个工作单元的记录读完、推上来,并结束它开着的会话 / 轮次 / 工具段**(`flush`,原因跟着 worklet 段;等不到就不等,迟到的点照收,段不重开,[work-node.md §7](work-node.md));已经归档的 work 里关掉工作单元不再 flush(归档时做过了)。
- **`agent.session`**(节点):看到一个新会话开始就开(Claude Code 的 `SessionStart` hook 报会话 id 和记录路径;没有 hook 的,看到这份记录的第一条);同一个会话 `/resume` 回来开新的一段,link 指向它的上一段。被下一个会话接替时结束(`replaced`),或 flush 时跟着 worklet 段结束(原因相同)。属性:`memorytalk.worklet.id`、`gen_ai.conversation.id`、`memorytalk.session.source`(`startup` / `resume` / `clear` / `compact`,有就记)、`gen_ai.system`、`memorytalk.unrecognized`(解析时不认识的记录条数,格式变了看得见)。
- **`agent.turn`**(节点):人的一条输入就开,起点 = 这条输入的时刻,它的 `agent.message` 是这一轮的第一个点。agent 收尾就结束——Claude Code 的 `Stop` hook,或 `stop_reason = end_turn` 而且没有待完成的工具调用;Codex 的 `task_complete`;Kimi 的 `turn.ended`——reason `completed`,status OK;被打断(Esc、`turn_aborted`、`turn.cancel`)reason `cancelled`,status OK;会话段或 worklet 段先结束了就跟着结束,终点取这一轮最后一条记录的时刻,status 跟着(`gone` 是 Unset)。**结束即定稿**,之后不再改。一轮中途人又插话(Kimi 的 `turn.steer`)记成这一轮上的一个 `agent.message`,不开新的一轮。属性:`memorytalk.worklet.id`、`gen_ai.operation.name`、token 数(§4)、`memorytalk.message.count`;**不记人**(轮次是 agent 的)——这句话是谁从哪送进去的,看 `memorytalk.input.id`([work-server-io.md §4.3](work-server-io.md))。
- **`agent.tool`**(节点):起点是工具调用那条记录的时刻,终点是对应结果那条记录的时刻;结果标了出错(Claude Code 的 `is_error` 之类)status 记 Error——这是唯一用到 Error 的地方;轮次先结束了(被打断)就跟着结束,reason `cancelled`。
- **时间**:节点按各家格式换算成 Unix 纳秒(Claude Code / Codex 是 ISO 串,Kimi 是**毫秒**数);解不出来的沿用前面最近一条。agent 点的 `timeUnixNano` 是记录里的时刻,`observedTimeUnixNano` 是中心收到的时刻;中心自己写的点两个一样。

**现场自己没了的 span**:worklet span 开着,可是 tmux 会话已经不在了(命令跑完了、机器重启了)。这由节点发现——它一直盯着本机的 tmux 会话——报 `gone`:把 span 结束掉,记 `memorytalk.end.reason = "gone"`,不记结束的人;终点取它最后一次确认还活着的时刻,span 的 `status` 保持 Unset,不当成 Error;里面开着的会话 / 轮次 / 工具段跟着结束。正在关掉 / 归档 / 重入的工作单元不判 `gone`(现场销毁了、段还没结束的那一会儿,段由那个动作自己结束或接着用)。正常关掉的,`memorytalk.end.reason = "detached"`,`status` 为 OK。

**重启**:`spans` 表里终点为空的行,重启后还是开着的。work span 本来就该一直开着;其余的靠对账:中心重启,节点重连后先对一遍([work-node.md §7](work-node.md))再接着推;节点重启,从中心问游标接着读。

## 6. 读:一份数据,三种视图

接口是 `GET /works/{id}/trace`,返回 `{"traces": TracesData, "logs": LogsData, "seq": "<这次读到的最大变更序号>"}`(OTLP/JSON,各一个 resource、一个 scope):结束的段、开着的段(没有 `endTimeUnixNano`,另带 `memorytalk.open = true`)、点;段按开始时间(再按 span id)排,点按时间(再按写入的先后)排。段带 `traceId` / `spanId` / `parentSpanId`(根段没有)/ `name` / `kind` / `startTimeUnixNano` / `endTimeUnixNano` / `attributes` / `links` / `status`;点带 `timeUnixNano` / `observedTimeUnixNano`(agent 点两个不一样,§5)/ `eventName` / `traceId` / `spanId` / `attributes`。参数:

| 参数 | 意思 |
|---|---|
| `subtree` | 默认 `false`;`true` 连同所有子孙 work |
| `worklet=<id>` | 只看一个工作单元 |
| `agent=1` | 带上 agent 那几层的段和点(默认只给 `work` / `worklet` 段和动作点——agent 的一条消息一个点,太多) |
| `bodies=1` | 带正文(默认不带,正文大) |
| `after=<seq>` | 只要这个变更序号之后新写的或改过的段和点(§3) |
| `wait=<秒>` | 配合 `after`:什么都没变就等着,有变化或超时才返回(长轮询) |
| `fields=cursors` | 只要推到哪了(节点重连时用,[work-node.md §6](work-node.md)) |

**这一个接口就是全部的读。** 人看的时间线和图(默认)、看一个工作单元的对话(`worklet` + `agent` + `bodies`)、界面等变化和程序接着读(再加 `after` + `wait`)。[work-server-io.md](work-server-io.md) 说的 output 就是它——没有单独的 output、messages、state 接口;状态就是 trace 里最新的 `agent.state` 点。

**写也是这个路径**:`POST /works/{id}/trace` 收同一个形状(§5、[work-node.md §6](work-node.md))——`GET` 出来的文档原样 `POST` 回去,意思不变。

**1)瀑布图(类似 Chrome DevTools 的 Network)**

- 一行一个 span,按树的先序排:work → 子 work → worklet → 会话 → 轮次 → 工具调用。可以折叠,缩进表示层级。
- 横轴是时间。条从 start 画到 end;开着的画到「现在」,尾巴做成渐隐。
- 颜色按 span 的 `name`:work / worklet / 会话 / 轮次 / 工具各一种;`gone` 结束的画成虚线,出错的工具调用标红。
- 点画在所属 span 的那一行上,是一个小刻度;鼠标悬停显示事件名、人、属性。
- 顶部有时间刷,可以框选缩放;按列、人、类型筛选。
- 右侧详情面板显示这个 span 的全部属性和 link,worklet 还带「打开窗」,agent 轮次还带「看这一轮的消息」。

**2)甘特图:同一张图,换了尺度和读法**

| 瀑布图 | 甘特图 |
|---|---|
| span | 任务条 |
| 父子 span | WBS 层级(大任务 / 子任务) |
| 点 | 里程碑(菱形) |
| link | 依赖箭头 |
| 开着的 span | 进行中的任务(条画到今天) |
| 时间轴以秒、分钟为主 | 时间轴以天、周为主 |

两种读法之间的切换,只是改一下缩放和行的粒度:甘特默认只显示 work 这一层(子 work 当子任务),worklet 和 agent 那几层折叠起来。放大到某一天,就回到瀑布图,能看到那天开了哪些终端、agent 跑了几轮、每轮多长、卡在哪个工具上。**这是从项目管理一路钻到可观测的那条路**:「这个子任务为什么拖了三天」→ 展开看到 agent 在第二天跑了四十轮都卡在同一个工具调用上 → 点进那一轮看它说了什么。

**3)动态(时间线列表)**

右侧原来的「动态」变成 trace 的一个列表视图(已实施,`shell/WorkEvents.tsx`;现在 5 秒整份拉一次,改成 `after` + `wait` 之后有变化才刷新):段的开始、段的结束(开着的只有开始)、点各一行,按时间排(纳秒比大小用 BigInt,同一时刻开始 < 点 < 结束),新的在上;写成人话,写法沿用 work-events.md §7。工作单元叫什么从它的 worklet 段上取(点按 `spanId` 找段);结束按 `memorytalk.end.reason` 写成关掉 / 归档 / 现场没了三种(`worklet.closed` 点也写成关掉);谁做的取 `user.id`,结束的取 `memorytalk.end.user.id`(没有再用 `user.id`),现场没了的不写人。`agent.*` 默认藏起来(会话、轮次、工具和消息太多,会把别的挤走),点一下展开。旧的 `GET /works/{id}/events` 撤了。

## 7. 计划:让甘特图有东西可比

trace 记的是**实际发生了什么**,可甘特图还要**计划**。计划作为 work 自己的字段(可选):

- `plan.start` / `plan.due`:打算什么时候开始、什么时候做完。存在 work 节点上,改了就打一个 `plan.changed` 点,所以计划怎么变过也在 trace 里。
- `depends_on: [work_id]`:这件事等着哪些事。存在 work 节点上,同时写成 work span 的 link。

甘特图上的一行因此有两条:**计划条**(淡色,从 `plan.start` 到 `plan.due`)和**实际条**(work span 的起止)。实际条比计划条长出来的那截就是延期,而且能一直往下钻到原因(§6)。可观测到项目管理的打通,落到实处就是这一件事:**计划和实际画在同一根时间轴上,实际那一侧能一直展开到每个终端、每一轮**。

## 8. 对外:三种接法

1. **什么都不接**:`worktrace.db` 就是真相来源,memory.talk 自己画图。
2. **Collector 读文件**:memory.talk 把已结束的段和所有的点按 OTLP/JSON 一行一条导出到 `<home>/trace-export/*.jsonl`(可选,默认关),用 Collector 的 `otlpjsonfile` receiver 盯住这个目录,转发到 Jaeger、Tempo 或者任何 OTLP 后端。这个 receiver 一个 pipeline 只解析一种信号;导出既然由 memory.talk 自己写,就直接分成 `traces-*.jsonl` 和 `logs-*.jsonl` 两种文件,各配一个 pipeline,不用去赌混合文件里另一种信号的行能不能被跳过。开着的段不在文件里,外面看到的是已经结束的段加上所有的点。
3. **进程内直推**:设置了 `OTEL_EXPORTER_OTLP_ENDPOINT` 这些标准环境变量,memory.talk 在写 `worktrace.db` 的同时,把同一条记录用 OTLP/HTTP 推出去(批量、失败只记日志,不影响写盘)。

**正文默认不往外发。** 导出和直推的 agent 点默认不带 `body`(只有结构、计数和 token),设了 `MEMORY_TALK_EXPORT_CONTENT=1` 才带——和 OTel GenAI 规范「内容默认不采」一个意思。

## 9. 迁移

- **不迁移旧事件。** 跟着 [work-store.md §7](work-store.md) 一起不做兼容:旧的 `events.jsonl` / `work_logs` 不转换、不读,work 数据重新开始。
- **工作单元编号**:原来给没有 `seq` 的旧 work 发号时要扫事件里出现过的 `-w<n>`;现在计数器是 `works.next_worklet` 列,新库里每个 work 从 1 开始,这段兜底逻辑删掉。
- **`rounds` 表和 `spans.first_round_id` 去掉,不迁移。** 已有的 round 不转成点,已有的 `agent.turn` 段留着不动;改完以后 agent 那几层只由节点推。
- **文档**:已同步改掉 work-events.md 的存储部分,以及 structure 里的 filesystem.md 和 work.md。

## 10. 这篇有意不定的事

- **开着的段要不要定期往外推一份快照**。外部后端现在只能看到已经结束的段,一个开了三周的 work 在 Jaeger 里是看不到的。可以定期发一个 `memorytalk.open = true` 的临时 span,但各家后端对同一个 span id 出现多次的处理不一样。先不做,开着的段只在 memory.talk 自己的图里看。
- **把 TRACEPARENT 注入到现场里**。打开工作单元时,在 tmux 会话的环境里设上 W3C 的 `TRACEPARENT`,值指向这个 worklet 的 span;这样现场里任何一个接了 OTel 的工具(比如打开了遥测的 agent CLI、测试框架)产生的 span,都会自动挂到这个工作单元下面。瀑布图可以一直钻到 agent 调了哪个工具、跑了多久。这要有一个 OTLP 接收端;节点就在现场旁边,可以当这个接收端,留到后面。
- **列要不要也做成 span**。列只是弱编排,本篇只把它当点(加、改名、删)。如果以后想在甘特图上按列分泳道,用 worklet span 上的 `memorytalk.column.id` 属性分组就够了,用不着列 span。
- ~~**agent 轮次怎么切**~~:已定——按各家记录里的收尾标记和 hooks 切(§5),不再按「到下一条人的输入之前」。
- **子 agent 的细节**:Claude Code 子 agent 的记录现在是在主会话里(`isSidechain`)还是单独的文件,按当前版本对一遍;挂法按 §2。
- **`/resume` 和 `/compact`**:resume 回来是新的一段会话(§4);compact 之后要不要也换一段,看 hooks 报的 `source` 再定。
- **agent 点要不要单独一张表或一个库**:正文让 `points` 变大以后,如果拖慢了列表和图的查询,把 `agent.*` 点拆出去,列不变,只是换个地方。
- **worktrace.db 会越来越大**。按时间切库还是把已结束的 work 导出归档后删掉,和 [work-store.md §8](work-store.md) 一起定。
