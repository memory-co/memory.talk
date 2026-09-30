# work-trace —— 把 events 换成 trace:OTel 格式,分点和段,一张图从可观测走到甘特(v5 设计)

> **状态:设计中,未实施。** 本篇把 work 的时间线从「一串事件」换成 **trace**:有起止的东西记成**段(span)**,瞬间发生的事记成**点(event)**,落盘格式就是 OpenTelemetry 的 **OTLP/JSON**,一行一条。这样做有三个目的:
>
> 1. 这份数据不用转换,就能交给 Collector、Jaeger、Tempo 这类可观测后端;
> 2. memory.talk 自己能画出类似 Chrome DevTools Network 那样的瀑布图;
> 3. 同一张瀑布图拉到「天」的尺度就是甘特图,可观测和项目管理用的是同一份数据。
>
> **落盘位置已改**:轨迹存在 `worktrace.db`(见 [work-store.md §5](work-store.md)),表的列和 OTel 字段一对一。§3 的 OTLP/JSON 是**对外的格式和字段规范**:接口返回、导出文件、OTLP 推送都用它;库里不存信封本身。
>
> 实施以后,本篇取代 [work-events.md](work-events.md) 的存储部分(动作表、列标记、`by` 这些规则保留)和 [work-store.md §6](work-store.md)。

相关:
- 现在的事件:一个动作一个请求,每条带列标记和 `by`: [work-events.md](work-events.md)
- 轨迹存在哪(`worktrace.db` 的 `spans` / `points` 表): [work-store.md §5](work-store.md)
- work 树、worklet 的身份: [work.md](work.md) / [worklet.md](worklet.md)
- agent 的 round(`rounds` 流,trace 只引用它): [work-server.md](work-server.md)
- OTLP/JSON 编码: <https://opentelemetry.io/docs/specs/otlp/#json-protobuf-encoding>;Collector 的 `otlpjsonfile` receiver / `file` exporter 读写的就是这种一行一条的格式

---

## 1. 为什么:events 只有点,可是 work 里的东西大多有长度

现在 `events.jsonl` 里每条都是一个时刻:`worklet.attached` 一条、`worklet.detached` 另一条。可是「这个终端从 10:02 开到 15:40」本来就是**一段时间**。拆成两个点以后:

- **想画条要自己配对**。拿 attached 和 detached 按 worklet id 配成一对,中间断了(服务重启、现场自己退出了)就配不上,只能靠猜。
- **没有层级**。子 work、work 里的终端、终端里 agent 的一轮,本来一层套一层;事件是平的,每条只能靠 `work_id` 挂到某个 work 下面。
- **外面接不了**。自造的 `{ts, type, data}` 格式,可观测那边没有一个工具认识;要接就得写一层转换。
- **跟项目管理是两套东西**。甘特图要的是「每件事从哪天到哪天、谁套着谁、谁卡着谁」,和 trace 瀑布图的结构一模一样,可现在两边的数据各记各的。

trace 模型本来就有这些:span 有起点和终点;父子关系决定层级;span 之间可以 link;一个时刻用 event 记。OTel 把这套东西标准化了,我们直接用。

## 2. 点和段:哪些是 span,哪些是 event

**段(span)= 有起止的东西。** 一个 span 有开始、有结束,可以套子 span。

| span | 起 | 止 | 父 |
|---|---|---|---|
| `work` | 建 work(`created`) | 归档(`archived`) | 父 work 的 `work` span;根 work 没有父 |
| `worklet` | 打开工作单元(`attached`) | 关掉(`detached`),或现场没了(§5) | 所在 work 的 `work` span |
| `agent.turn` | agent 工作单元里,人发出的一条输入 | agent 这一轮最后一条输出 | 所在 worklet 的 span |

**点(event)= 一个时刻发生的事。** 点没有长度,但它总挂在某个 span 上,意思是「在这段时间里的某一刻发生了这件事」。

| 点 `event.name` | 挂在 | 属性(除 `user.id` 外) |
|---|---|---|
| `work.renamed` | work span | `memorytalk.work.goal`、`memorytalk.from` |
| `column.added` / `column.renamed` / `column.removed` | work span | `memorytalk.column.id`、`memorytalk.column.alias`(`renamed` 另有 `memorytalk.from`) |
| `worklet.moved` | worklet span | `memorytalk.column.id` / `.alias` 和 `memorytalk.index`(去哪),`memorytalk.from.column.id` / `.alias` 和 `memorytalk.from.index`(从哪) |
| `plan.changed` | work span | `memorytalk.plan.start` / `memorytalk.plan.due`(§7) |

现在 `events` 里的每一种都有着落:

| 现在的事件 | trace 里 |
|---|---|
| `created` | `work` span 的开始 |
| `status`(→ `archived`)/ `frozen` | `work` span 的结束。冻结和归档是同一个时刻,一个 span 结束就够了,不再单记 |
| `status`(`archived` → `running`,重新打开) | 开一个新的 `work` span:同一个 work id,新的 span id,用 link 指向上一段(§4)。甘特上同一行出现两段 |
| `worklet.attached` / `worklet.detached` | `worklet` span 的开始 / 结束 |
| `worklet.moved`、`column.*` | 点 |

收起 / 展开仍然不记(同 work-events.md §2)。收件箱和 round 不进 trace:收件箱是别的 work 打过来的消息,不是这个 work 自己的经过;round 是内容,trace 只记这一轮的起止和计数,正文仍在 `rounds` 流里,通过 `memorytalk.round.first` / `memorytalk.round.last` 引用。

## 3. 格式:OTLP/JSON(落盘在 worktrace.db)

> 下面讲的「一行一个信封」是**导出格式**(`trace.jsonl`):导出文件是这个样子,`GET /trace` 返回的也是这些信封。真相来源是 `worktrace.db`,见本节末尾。

**一行一个完整的 OTLP 信封**,内容是 Collector `file` exporter 写出来的那种。行分两种,看顶层 key 就能区分:

- **段** = `{"resourceSpans": [...]}`,里面装**一个已经结束的** span;
- **点** = `{"resourceLogs": [...]}`,里面装**一条** log record,带 `eventName`,再用 `traceId` / `spanId` 挂到所属的 span 上。

点用 log record 表示,不塞进 span 的 `events[]`,原因有两个。第一,span 在结束时才整条写出(见下),而点要在发生的当下就落盘;一个 work span 可能开几个月,把点攒在它的 `events[]` 里,等于这几个月都不落盘。第二,OTel 已经把「有名字的事件」统一到 Logs 信号上(LogRecord 的 `event_name` 字段),Span Events 正在往这个方向收拢;按新的做法来,后端那边也是按 trace / span id 关联起来显示。

段的一行(换行和缩进只为好读,实际是一行):

```json
{"resourceSpans":[{"resource":{"attributes":[
    {"key":"service.name","value":{"stringValue":"memory.talk"}},
    {"key":"service.instance.id","value":{"stringValue":"<实例 id>"}}]},
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
        {"key":"memorytalk.worklet.server","value":{"stringValue":"bash"}},
        {"key":"memorytalk.column.id","value":{"stringValue":"c3"}},
        {"key":"memorytalk.column.alias","value":{"stringValue":"测试"}},
        {"key":"user.id","value":{"stringValue":"alice"}},
        {"key":"memorytalk.end.user.id","value":{"stringValue":"bob"}},
        {"key":"memorytalk.end.reason","value":{"stringValue":"detached"}}],
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
        {"key":"memorytalk.from.column.id","value":{"stringValue":"c3"}},
        {"key":"memorytalk.from.index","value":{"intValue":"0"}},
        {"key":"memorytalk.column.id","value":{"stringValue":"c1"}},
        {"key":"memorytalk.index","value":{"intValue":"1"}}]}]}]}]}
```

编码规则都按 OTLP/JSON 规范来:`traceId` / `spanId` 用十六进制字符串(不用 base64);64 位整数(时间戳、`intValue`)写成十进制字符串;`kind` 和 `status.code` 写成整数;字段名是 lowerCamelCase。属性分两类:

- **通用语义约定里有的,用标准名**:`service.name`、`user.id`,以后还有 GenAI 的 `gen_ai.*`(§4);
- **我们自己的,一律放在 `memorytalk.*` 命名空间下**。

**段在结束时才写,写的时候是整条。** OTLP 里的 span 是一条不可变的完整记录,没有「先写开头、再补结尾」这回事。所以:

- 导出的 `trace.jsonl` 只收**已经结束**的 span 和所有的点,真正做到只追加,Collector 的 `otlpjsonfile` receiver 能直接读;
- **还开着的 span** 不出现在导出里(OTLP 没有「开着的 span」),只在 memory.talk 自己的图里画出来。

**真相来源是 `worktrace.db`**([work-store.md §5](work-store.md)):

| 表 | 装什么 |
|---|---|
| `spans` | 一行一个段,列和 OTLP span 一对一;**`end_time_unix_nano` 为空 = 还开着**,结束时在同一行补上终点。开着的段不用再另存一份状态 |
| `points` | 一行一个点,列和 OTLP log record 一对一,只追加 |

每行带 `work_id`(属于哪个 work)和 `trace_id`(属于哪棵树):一个 work 的轨迹按 `work_id` 查,整棵树按 `trace_id` 查。

## 4. id:一棵 work 树是一条 trace

- **trace id = 根 work**:`traceId = sha256("memorytalk/trace/" + 根 work id)` 的前 16 字节。一棵 work 树从根到叶都在同一条 trace 里,所以不管在瀑布图还是甘特图上,一次就能看到整件事。子 work 不单独开 trace。
- **span id 由身份算出来**:work span 是 `sha256("memorytalk/span/work/" + work id + "/" + 第几段)` 的前 8 字节(第几段见 §2 的「重新打开」);worklet span 同理,用 worklet id 算;agent 轮次用随机数。算得出来就不用查:子 work 知道自己的父 span id,打开工作单元时也知道它该挂在哪个 work span 下面。
- **link = 依赖**:span 的 `links[]` 用来表示「这件事等着那件事」(§7 的依赖),以及「重新打开的这一段接的是上一段」。link 在 span 开着的时候写在 `spans` 表那一行的 `links` 列里,可以随时加,导出时随整条一起写出。
- **不能挪树**:trace id 取决于根,所以 work 不能换父(现在本来也不能,local 形态的目录就是树)。

**agent 轮次对上 GenAI 语义约定。** `agent.turn` span 的属性用 OTel GenAI 的标准名:`gen_ai.system`(`anthropic` / `openai` / …)、`gen_ai.operation.name`、`gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens`(adapter 能读到就填)。这样可观测那边现成的 LLM 看板能直接用。

## 5. 写:谁在什么时候开段、关段、打点

原来的 `Events` 换成一个 `Trace` 服务,只有三个动作:

```
start(work_id, name, span_id, parent_span_id, attributes, links=[])  → spans 表插一行,终点为空
end(work_id, span_id, attributes={}, status=OK)                       → spans 表那一行补上终点;导出一条完整的 span
point(work_id, span_id, event_name, attributes)                       → points 表追加一行;导出一条 log record
```

写入顺序沿用 [work-store.md §7](work-store.md):先改快照(登记、画布),再动 trace;trace 写失败不回滚快照。每条都带 `user.id`,取登录态里的人。结束一个 span 的人如果不是开它的人,另记 `memorytalk.end.user.id`。

**现场自己没了的 span**:worklet span 开着,可是 tmux 会话已经不在了(命令跑完了、机器重启了)。这种情况在列清单或者服务启动的时候发现,就把 span 结束掉,记 `memorytalk.end.reason = "gone"`;终点取「最后一次确认还活着的时刻」,span 的 `status` 保持 Unset,不当成 Error。正常关掉的,`memorytalk.end.reason = "detached"`,`status` 为 OK。

**服务重启**:`spans` 表里终点为空的行,重启后还是开着的。work span 本来就该一直开着;worklet span 按上一条对一遍现场。

## 6. 读:一份数据,三种视图

新接口是 `GET /works/{id}/trace?subtree=1`,返回一个 OTLP/JSON 的 `TracesData` 加一个 `LogsData`:结束的段、开着的段(没有终点,另带 `memorytalk.open = true`)、所有的点。前端画图只用这一个接口。

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

右侧原来的「动态」变成 trace 的一个列表视图:按时间排,把段的开始、段的结束、点都写成人话,写法沿用 work-events.md §7。旧的 `GET /works/{id}/events` 撤掉。

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
- **文档**:实施的时候同步改掉 work-events.md 的存储部分,以及 structure 里的 filesystem.md 和 work.md。

## 10. 这篇有意不定的事

- **开着的段要不要定期往外推一份快照**。外部后端现在只能看到已经结束的段,一个开了三周的 work 在 Jaeger 里是看不到的。可以定期发一个 `memorytalk.open = true` 的临时 span,但各家后端对同一个 span id 出现多次的处理不一样。先不做,开着的段只在 memory.talk 自己的图里看。
- **把 TRACEPARENT 注入到现场里**。打开工作单元时,在 tmux 会话的环境里设上 W3C 的 `TRACEPARENT`,值指向这个 worklet 的 span;这样现场里任何一个接了 OTel 的工具(比如打开了遥测的 agent CLI、测试框架)产生的 span,都会自动挂到这个工作单元下面。瀑布图可以一直钻到 agent 调了哪个工具、跑了多久。这要 memory.talk 自己当 OTLP 接收端,或者从 Collector 读回来,工作量不小,留到后面。
- **列要不要也做成 span**。列是布局,本篇只把它当点(加、改名、删)。如果以后想在甘特图上按列分泳道,用 worklet span 上的 `memorytalk.column.id` 属性分组就够了,用不着列 span。
- **agent 轮次怎么切**。「一轮」从 adapter 读到的 round 里切出来,不同的 agent CLI 标记方式不一样。第一版只按「人的一条输入到下一条人的输入之前」来切。
- **worktrace.db 会越来越大**。按时间切库还是把已结束的 work 导出归档后删掉,和 [work-store.md §8](work-store.md) 一起定。
