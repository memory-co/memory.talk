# work-trace —— 把 events 换成 trace:OTel 格式,分点和段,一张图从可观测走到甘特(v5 设计)

> **状态:部分实施。** 已经有了:落盘(`worktrace.db` 的 `spans` / `points` / `rounds`)、`work` / `worklet` / `agent.turn` 三种段、§2 的点(`plan.changed` 除外)、`GET /works/{id}/trace`(§6)、右侧「动态」列表(§6 的第 3 种视图)。还没做:瀑布图 / 甘特图(§6 的 1、2)、计划(§7)、往外导出和直推(§8 的 2、3)、服务启动时对一遍开着的 worklet 段(§5)。代码在 `services/work/trace.py`(写和读)、`services/work/turns.py`(切轮次)。
>
> 本篇把 work 的时间线从「一串事件」换成 **trace**:有起止的东西记成**段(span)**,瞬间发生的事记成**点(event)**,落盘格式就是 OpenTelemetry 的 **OTLP/JSON**,一行一条。这样做有三个目的:
>
> 1. 这份数据不用转换,就能交给 Collector、Jaeger、Tempo 这类可观测后端;
> 2. memory.talk 自己能画出类似 Chrome DevTools Network 那样的瀑布图;
> 3. 同一张瀑布图拉到「天」的尺度就是甘特图,可观测和项目管理用的是同一份数据。
>
> **落盘位置已改**:轨迹存在 `worktrace.db`(见 [work-store.md §5](work-store.md)),表的列和 OTel 字段一对一。§3 的 OTLP/JSON 是**对外的格式和字段规范**:接口返回、导出文件、OTLP 推送都用它;库里不存信封本身。
>
> 本篇已经取代 [work-events.md](work-events.md) 的存储部分(动作表、列标记、`by` 这些规则保留)。

相关:
- 现在的事件:一个动作一个请求,每条带列标记和 `by`: [work-events.md](work-events.md)
- 轨迹存在哪(`worktrace.db` 的 `spans` / `points` 表): [work-store.md §5](work-store.md)
- work 树、worklet 的身份: [work.md](work.md) / [worklet.md](worklet.md)
- agent 的 round(`rounds` 流,trace 只引用它): [work-server.md](work-server.md)
- OTLP/JSON 编码: <https://opentelemetry.io/docs/specs/otlp/#json-protobuf-encoding>;Collector 的 `otlpjsonfile` receiver / `file` exporter 读写的就是这种一行一条的格式

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

| span | 起 | 止 | 父 |
|---|---|---|---|
| `work` | 建 work(`created`);重新打开(新的一段) | 归档(`archived`) | 父 work 最新的一段 `work` span;根 work 没有父 |
| `worklet` | 打开工作单元(`attached`);重入时没有开着的段就开新的一段;work 重新打开时现场还活着的(网页的)也开新的一段 | 关掉(`detached`)、所在 work 归档(`archived`),或现场没了(`gone`,§5) | 所在 work 最新的一段 `work` span |
| `agent.turn` | agent 工作单元里,人发出的一条输入 | 下一条人的输入之前的最后一条 round;还没有下一条就开着,worklet 段结束时跟着结束 | 所在 worklet 最新的一段 span |

**点(event)= 一个时刻发生的事。** 点没有长度,但它总挂在某个 span 上,意思是「在这段时间里的某一刻发生了这件事」。

| 点 `event.name` | 挂在 | 属性(除 `user.id` 外) |
|---|---|---|
| `work.renamed` | work span | `memorytalk.work.goal`、`memorytalk.from` |
| `column.added` / `column.renamed` / `column.removed` | work span | `memorytalk.column.id`、`memorytalk.column.alias`(`renamed` 另有 `memorytalk.from`;别名真变了才记) |
| `worklet.moved` | 这个工作单元最新的一段 worklet span | `memorytalk.worklet.id`,`memorytalk.column.id` / `.alias` 和 `memorytalk.index`(去哪),`memorytalk.from.column.id` / `.alias` 和 `memorytalk.from.index`(从哪);位置真变了才记 |
| `worklet.closed` | 这个工作单元最新的一段 worklet span | `memorytalk.worklet.id`、`memorytalk.column.id` / `.alias`(关的时候在哪一列);关掉时它已经没有开着的段(现场没了 / 归档过、重新打开后没重入)才记,段不再动 |
| `plan.changed` | work span | `memorytalk.plan.start` / `memorytalk.plan.due`(§7,还没做) |

原来 `events` 里的每一种都有着落:

| 原来的事件 | trace 里 |
|---|---|
| `created` | `work` span 的开始 |
| `status`(→ `archived`)/ `frozen` | `work` span 的结束。冻结和归档是同一个时刻,一个 span 结束就够了,不再单记 |
| `status`(`archived` → `running`,重新打开) | 开一个新的 `work` span:同一个 work id,新的 span id,用 link 指向上一段(§4)。甘特上同一行出现两段 |
| `worklet.attached` / `worklet.detached` | `worklet` span 的开始 / 结束;关的时候段已经结束了,记一个 `worklet.closed` 点 |
| `worklet.moved`、`column.*` | 点 |
| (改目标,原来不记) | `work.renamed` 点 |

收起 / 展开仍然不记(同 work-events.md §2)。收件箱和 round 不进 trace:收件箱是别的 work 打过来的消息,不是这个 work 自己的经过;round 是内容,trace 只记这一轮的起止和计数,正文在 `worktrace.db` 的 `rounds` 表里,通过 `memorytalk.round.first` / `memorytalk.round.last` 引用。

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

编码规则都按 OTLP/JSON 规范来:`traceId` / `spanId` 用十六进制字符串(不用 base64);64 位整数(时间戳、`intValue`)写成十进制字符串;`kind` 和 `status.code` 写成整数;字段名是 lowerCamelCase。属性分两类:

- **通用语义约定里有的,用标准名**:`service.name`、`user.id`,还有 GenAI 的 `gen_ai.*`(§4;现在 `agent.turn` 上有 `gen_ai.system`);
- **我们自己的,一律放在 `memorytalk.*` 命名空间下**。

**段在结束时才写,写的时候是整条。** OTLP 里的 span 是一条不可变的完整记录,没有「先写开头、再补结尾」这回事。所以:

- 导出的 `trace.jsonl` 只收**已经结束**的 span 和所有的点,真正做到只追加,Collector 的 `otlpjsonfile` receiver 能直接读;
- **还开着的 span** 不出现在导出里(OTLP 没有「开着的 span」),只在 memory.talk 自己的图里画出来。

**真相来源是 `worktrace.db`**([work-store.md §5](work-store.md)):

| 表 | 装什么 |
|---|---|
| `spans` | 一行一个段,列和 OTLP span 一对一;**`end_time_unix_nano` 为空 = 还开着**,结束时在同一行补上终点。开着的段不用再另存一份状态 |
| `points` | 一行一个点,列和 OTLP log record 一对一,只追加 |
| `rounds` | agent 的 round,只追加;`agent.turn` 段从这里切出来 |

每行带 `work_id`(属于哪个 work)和 `trace_id`(属于哪棵树):一个 work 的轨迹按 `work_id` 查,整棵树按 `trace_id` 查。

## 4. id:一棵 work 树是一条 trace

- **trace id = 根 work**:`traceId = sha256("memorytalk/trace/" + 根 work id)` 的前 16 字节。一棵 work 树从根到叶都在同一条 trace 里,所以不管在瀑布图还是甘特图上,一次就能看到整件事。子 work 不单独开 trace。
- **span id 由身份算出来**:work span 是 `sha256("memorytalk/span/work/" + work id + "/" + 第几段)` 的前 8 字节(第几段 = 这个 work 已经有几段 work 段,第一段是 0;见 §2 的「重新打开」);worklet span 同理,用 worklet id 算;agent 轮次用 `sha256("memorytalk/span/turn/" + worklet id + "/" + 这一轮第一条 round 的 id)` 的前 8 字节——同一轮再同步一次还是同一个 id,按它幂等改(`spans.first_round_id` 存的就是这条 round 的 id)。算得出来就不用查:子 work 知道自己的父 span id,打开工作单元时也知道它该挂在哪个 work span 下面。
- **link = 依赖**:span 的 `links[]` 用来表示「这件事等着那件事」(§7 的依赖),以及「重新打开的这一段接的是上一段」。link 写在 `spans` 表那一行的 `links` 列里(OTLP 的 `{traceId, spanId, attributes}`),导出时随整条一起写出。现在只有重新打开时写,开段那一刻一起写;依赖的 link 等 §7。
- **不能挪树**:trace id 取决于根,所以 work 不能换父(现在本来也不能:`PATCH /works/{id}` 只改目标和状态)。

**agent 轮次对上 GenAI 语义约定。** `agent.turn` span 的属性用 OTel GenAI 的标准名:`gen_ai.system`(`anthropic` / `openai` / …)、`gen_ai.operation.name`、`gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens`(adapter 能读到就填)。这样可观测那边现成的 LLM 看板能直接用。现在只填了 `gen_ai.system`(由 worklet 段上的 `memorytalk.worklet.server` 定),adapter 还读不到操作名和 token 数。

## 5. 写:谁在什么时候开段、关段、打点

原来的 `Events` 换成一个 `Trace` 服务,只有三个动作:

```
start(work_id, name, span_id, parent_span_id, attributes, *, user, worklet_id, links, at, first_round_id)
    → spans 表插一行:终点为空,status Unset;trace id 由根 work 算
end(span_id, attributes, *, status=OK, user, at)
    → 同一行补上终点、status、end_user_id,结束时的属性并进 attributes;已经结束的不再动(两处同时结束,只算先到的)
point(work_id, span_id, event_name, attributes, *, user, worklet_id, column_number)
    → points 表追加一行
```

往外导出(§8)还没做,所以现在三个动作只写库。「查一下再写」的几处(第几段、还开着没有、轮次有没有)包在 `worktrace.db` 的一个事务里。

写入顺序沿用 [work-store.md §6](work-store.md):先改快照(登记、画布),再动 trace;trace 写失败只记日志,不让动作失败,也不回滚快照。带身份的都写 `user.id`(同时进 `spans.user_id` / `points.user_id` 列),取登录态里的人;没有人的就不写(`agent.turn`、`gone`)。结束一个 span 的时候,结束它的人记在 `memorytalk.end.user.id`(和 `spans.end_user_id` 列;是开它的同一个人也记),怎么结束的记在 `memorytalk.end.reason`(`detached` / `archived` / `gone`);worklet 段另记结束那一刻在哪一列(`memorytalk.end.column.id` / `.alias`)。worklet 段开的时候带 `memorytalk.worklet.uri`(原样的 uri)/ `.scheme` / `.server` 和当时的列。

各种段什么时候开、什么时候结束:

- **`work`**:建 work 时开;归档时先把这个 work 开着的 worklet 段都结束(reason `archived`),再结束 work 段(结束的是这个 work 所有还开着的 work 段,不只是最新的一段);重新打开是新的一段,link 指向上一段,带 `memorytalk.work.reopened = true`。一个 work 同时只有一段 work 段开着:归档要收 round、逐个销毁现场,做完才结束段,这中间别人重新打开、打开或重入工作单元都得等它做完(同一个 work 的这几个动作在服务里排队,[work-store.md §6](work-store.md));重新打开时上一段还开着(那次归档的轨迹没写进去),先按归档补上终点(reason `archived`,终点取 `works.archived_at`,不记人),上一段里还开着的 worklet 段一样。
- **`worklet`**:打开工作单元时开(登记写进 `works.db` 之后);关掉时结束(`detached`,status OK,登记删掉之后);归档时结束(`archived`,status OK);重入时这个工作单元没有开着的段才开新的一段(父是 work 最新的一段;work 已归档不能重入,409——不然结束了的 work 段下面会开着一段 worklet 段,重新打开时又被补成长度为 0 的 `archived`);work 重新打开时,现场还活着的工作单元(网页的一直活着,没人会去重连)同样接着开新的一段,开的人记重新打开的人。关掉时已经没有开着的段(现场没了、归档过又重新打开还没重入),段不再动,在它最新的一段上打一个 `worklet.closed` 点记下谁在哪一列关的。关掉和归档之前,先从把手最后收一次 round(尽力而为,失败不挡动作);已经归档的 work 里关掉工作单元不再收(归档时收过最后一次,冻住的 round 不再追加)。
- **`agent.turn`**:不由某个动作开关,而是**同步 round 的时候从 round 里切出来**(`GET …/rounds` 拉到新 round 时,以及关掉 / 归档前那最后一次):人的一条输入(role `human`)起、到下一条人的输入之前算一轮,第一条人的输入之前的 round 不属于任何一轮;有下一条人的输入,这一轮就结束(终点 = 它最后一条 round 的时刻,status OK),没有就开着;worklet 段结束时,开着的轮次跟着结束,终点同样取它最后一条 round 的时刻,status 跟 worklet 段一样(`gone` 就还是 Unset)。结束了的轮次不再打开:之后又同步进来、还属于它的 round 只把终点往后挪。每次同步进来新 round 就把这个工作单元的 round 整个重切一遍,按 `first_round_id` 幂等写:没有就插,终点 / status / 属性变了就原地改;父和 trace id 取这个工作单元最新的一段 worklet 段。时间取 round 自己的时刻,各 adapter 写法不同(Claude Code / Codex 是 ISO 串,Kimi 是 Unix 秒),统一成 Unix 纳秒;解不出来的沿用前面最近一条,一轮里一个时刻都没有就不出这一轮。属性:`memorytalk.worklet.id`、`memorytalk.round.first` / `.last` / `.count`、`gen_ai.system`(claude → `anthropic`,codex → `openai`,kimi → `moonshot`);**不记人**(轮次是 agent 的,不是读 round 的那个人的)。

**现场自己没了的 span**:worklet span 开着,可是 tmux 会话已经不在了(命令跑完了、机器重启了)。这种情况在列清单或者服务启动的时候发现,就把 span 结束掉,记 `memorytalk.end.reason = "gone"`,不记结束的人;终点取「最后一次确认还活着的时刻」,span 的 `status` 保持 Unset,不当成 Error。现在只在列清单(`GET …/worklets`)时发现,终点取的是发现它没了的时刻(还没记最后一次活着);服务启动时对一遍还没做。正在关掉 / 归档 / 重入的工作单元不判 `gone`(现场销毁了、段还没结束的那一会儿,段由那个动作自己结束或接着用),结束之前再看一眼现场,刚被重入开起来的也不算。正常关掉的,`memorytalk.end.reason = "detached"`,`status` 为 OK。

**服务重启**:`spans` 表里终点为空的行,重启后还是开着的。work span 本来就该一直开着;worklet span 按上一条对一遍现场(还没做:现在要等下一次列清单才结束成 `gone`)。

## 6. 读:一份数据,三种视图

新接口是 `GET /works/{id}/trace`,返回 `{"traces": TracesData, "logs": LogsData}`(OTLP/JSON,各一个 resource、一个 scope):结束的段、开着的段(没有 `endTimeUnixNano`,另带 `memorytalk.open = true`)、所有的点;段按开始时间(再按 span id)排,点按写入的先后排。段带 `traceId` / `spanId` / `parentSpanId`(根段没有)/ `name` / `kind` / `startTimeUnixNano` / `endTimeUnixNano` / `attributes` / `links` / `status`;点带 `timeUnixNano` / `observedTimeUnixNano`(同一个值)/ `eventName` / `traceId` / `spanId` / `attributes`。`subtree` 默认 `false`,`true` 连同所有子孙 work。前端画图只用这一个接口。

**1)瀑布图(类似 Chrome DevTools 的 Network)**

- 一行一个 span,按树的先序排:work → 子 work → worklet → agent 轮次。可以折叠,缩进表示层级。
- 横轴是时间。条从 start 画到 end;开着的画到「现在」,尾巴做成渐隐。
- 颜色按 span 的 `name`:work / worklet / agent 轮次各一种;`gone` 结束的画成虚线。
- 点画在所属 span 的那一行上,是一个小刻度;鼠标悬停显示事件名、人、属性。
- 顶部有时间刷,可以框选缩放;按列、人、类型筛选。
- 右侧详情面板显示这个 span 的全部属性和 link,worklet 还带「打开窗」,agent 轮次还带「看 round」。

**2)甘特图:同一张图,换了尺度和读法**

| 瀑布图 | 甘特图 |
|---|---|
| span | 任务条 |
| 父子 span | WBS 层级(大任务 / 子任务) |
| 点 | 里程碑(菱形) |
| link | 依赖箭头 |
| 开着的 span | 进行中的任务(条画到今天) |
| 时间轴以秒、分钟为主 | 时间轴以天、周为主 |

两种读法之间的切换,只是改一下缩放和行的粒度:甘特默认只显示 work 这一层(子 work 当子任务),worklet 和 agent 轮次折叠起来。放大到某一天,就回到瀑布图,能看到那天开了哪些终端、agent 跑了几轮、每轮多长。**这是从项目管理一路钻到可观测的那条路**:「这个子任务为什么拖了三天」→ 展开看到 agent 在第二天跑了四十轮都卡在同一个地方 → 点进 round 看它说了什么。

**3)动态(时间线列表)**

右侧原来的「动态」变成 trace 的一个列表视图(已实施,`shell/WorkEvents.tsx`,5 秒拉一次):段的开始、段的结束(开着的只有开始)、点各一行,按时间排(纳秒比大小用 BigInt,同一时刻开始 < 点 < 结束),新的在上;写成人话,写法沿用 work-events.md §7。工作单元叫什么从它的 worklet 段上取(点按 `spanId` 找段);结束按 `memorytalk.end.reason` 写成关掉 / 归档 / 现场没了三种(`worklet.closed` 点也写成关掉);谁做的取 `user.id`,结束的取 `memorytalk.end.user.id`(没有再用 `user.id`),现场没了的不写人。`agent.turn` 默认藏起来(一轮两行,会把别的挤走),点一下展开。旧的 `GET /works/{id}/events` 撤了。

## 7. 计划:让甘特图有东西可比

trace 记的是**实际发生了什么**,可甘特图还要**计划**。计划作为 work 自己的字段(可选):

- `plan.start` / `plan.due`:打算什么时候开始、什么时候做完。存在 work 节点上,改了就打一个 `plan.changed` 点,所以计划怎么变过也在 trace 里。
- `depends_on: [work_id]`:这件事等着哪些事。存在 work 节点上,同时写成 work span 的 link。

甘特图上的一行因此有两条:**计划条**(淡色,从 `plan.start` 到 `plan.due`)和**实际条**(work span 的起止)。实际条比计划条长出来的那截就是延期,而且能一直往下钻到原因(§6)。可观测到项目管理的打通,落到实处就是这一件事:**计划和实际画在同一根时间轴上,实际那一侧能一直展开到每个终端、每一轮**。

## 8. 对外:三种接法

1. **什么都不接**:`worktrace.db` 就是真相来源,memory.talk 自己画图。
2. **Collector 读文件**:memory.talk 把已结束的段和所有的点按 OTLP/JSON 一行一条导出到 `<home>/trace-export/*.jsonl`(可选,默认关),用 Collector 的 `otlpjsonfile` receiver 盯住这个目录,转发到 Jaeger、Tempo 或者任何 OTLP 后端。这个 receiver 一个 pipeline 只解析一种信号;导出既然由 memory.talk 自己写,就直接分成 `traces-*.jsonl` 和 `logs-*.jsonl` 两种文件,各配一个 pipeline,不用去赌混合文件里另一种信号的行能不能被跳过。开着的段不在文件里,外面看到的是已经结束的段加上所有的点。
3. **进程内直推**:设置了 `OTEL_EXPORTER_OTLP_ENDPOINT` 这些标准环境变量,memory.talk 在写 `worktrace.db` 的同时,把同一条记录用 OTLP/HTTP 推出去(批量、失败只记日志,不影响写盘)。

## 9. 迁移

- **不迁移旧事件。** 跟着 [work-store.md §7](work-store.md) 一起不做兼容:旧的 `events.jsonl` / `work_logs` 不转换、不读,work 数据重新开始。
- **工作单元编号**:原来给没有 `seq` 的旧 work 发号时要扫事件里出现过的 `-w<n>`;现在计数器是 `works.next_worklet` 列,新库里每个 work 从 1 开始,这段兜底逻辑删掉。
- **文档**:已同步改掉 work-events.md 的存储部分,以及 structure 里的 filesystem.md 和 work.md。

## 10. 这篇有意不定的事

- **开着的段要不要定期往外推一份快照**。外部后端现在只能看到已经结束的段,一个开了三周的 work 在 Jaeger 里是看不到的。可以定期发一个 `memorytalk.open = true` 的临时 span,但各家后端对同一个 span id 出现多次的处理不一样。先不做,开着的段只在 memory.talk 自己的图里看。
- **把 TRACEPARENT 注入到现场里**。打开工作单元时,在 tmux 会话的环境里设上 W3C 的 `TRACEPARENT`,值指向这个 worklet 的 span;这样现场里任何一个接了 OTel 的工具(比如打开了遥测的 agent CLI、测试框架)产生的 span,都会自动挂到这个工作单元下面。瀑布图可以一直钻到 agent 调了哪个工具、跑了多久。这要 memory.talk 自己当 OTLP 接收端,或者从 Collector 读回来,工作量不小,留到后面。
- **列要不要也做成 span**。列是布局,本篇只把它当点(加、改名、删)。如果以后想在甘特图上按列分泳道,用 worklet span 上的 `memorytalk.column.id` 属性分组就够了,用不着列 span。
- **agent 轮次怎么切**。「一轮」从 adapter 读到的 round 里切出来,不同的 agent CLI 标记方式不一样。第一版只按「人的一条输入到下一条人的输入之前」来切。
- **worktrace.db 会越来越大**。按时间切库还是把已结束的 work 导出归档后删掉,和 [work-store.md §8](work-store.md) 一起定。
