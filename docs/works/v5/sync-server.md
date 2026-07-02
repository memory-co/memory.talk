# sync-server — 把 sync 剥成独立服务,一源一 worker(v5 设计)

> **状态:设计中。** 把现在进程内的 sync(`service/sync.py` 的 SyncWatcher + adapters)**整个剥离出去**,变成一个**独立服务**,与 [seekbase](seekbase.md) **平级**(v5 的两个基础服务:seekbase 管数据,sync-server 管摄入边界)。内部按**数据来源**拆成一个个 **worker**:每个来源一个 worker,各自**监听**自己的上游、把上游私有格式**整理成标准 session 格式**、再**发**进 memory system。

相关:
- 数据层(sync-server 不直接碰它,见 §4): [seekbase.md](seekbase.md)
- v5 立意(sync-server 在架构里的位置): [README.md](README.md)
- 现状(要被剥离的东西): [`memorytalk/service/sync.py`](../../../memorytalk/service/sync.py) · [`memorytalk/adapters/`](../../../memorytalk/adapters/)

---

## 1. 为什么剥出去

现在 sync 是 memory daemon 进程内的一个 watcher(watchdog 事件 + 冷扫 backfill),三个 adapter(claude-code / codex / openclaw)编译在主进程里。剥离的理由:

- **职责本来就不同**:sync 是「**连接外部世界**」的 connector 层——`sync.db` 的设计注释早就把话说透了(*"connector-state concern, not a memory concern"*)。它认识的是上游文件格式、游标、sha;memory system 认识的是 session / card。两个 domain 焊在一个进程里只是历史巧合。
- **故障隔离**:上游格式变了、watchdog 抽风、某个来源的文件损坏——这些**摄入侧的故障不该能拖垮 memory daemon**(反之亦然:memory 重启不该丢监听)。
- **来源会越来越多**:v5 之后接新来源(更多 agent 工具、浏览器、聊天记录……)应该是**加一个 worker**,而不是改主进程再发版。
- **云端形态的必然**(呼应 seekbase §9):memory 在云上时,**采集必须留在数据所在的机器上**——sync-server 天然是「跑在用户机器上的采集端」,经 HTTP 把经验推给远端 memory。剥离就是把这条边界现在就切对。

## 2. 形态:独立服务,memory 的一个普通客户端

```
   上游(各机器上的数据来源)                sync-server(独立进程)                memory system
  ┌─────────────────────────┐      ┌──────────────────────────────┐      ┌─────────────────┐
  │ ~/.claude/…(jsonl)      │◀─监听─│ worker: claude-code           │      │                 │
  │ ~/.codex/…              │◀─监听─│ worker: codex                 │─推送─▶│  ingest 接口     │
  │ openclaw 目录            │◀─监听─│ worker: openclaw              │ HTTP │ (ensure_session │
  │ (未来:浏览器/聊天/邮件…) │◀─监听─│ worker: …(一源一个,可插拔)   │      │  append_rounds) │
  └─────────────────────────┘      │ 自己的 checkpoint 库(sync.db) │      └────────┬────────┘
                                   └──────────────────────────────┘               seekbase
```

- **独立进程、独立生命周期**:自己启停、自己的日志与状态,和 memory daemon 互不陪葬;
- **对 memory 只是一个客户端**:经 **ingest 接口**(HTTP)推数据——`ensure_session`(问服务端游标)+ `append_rounds`(乐观并发追加),这套现有契约就是剥离面,基本不用发明新东西;
- **checkpoint 归它**:`sync.db`(每源的 sha / last_round_id / offset)跟着 sync-server 走——「上游我看到哪了」本来就是 connector 状态;
- **与 seekbase 平级**:两个都是基础服务——**seekbase 管「数据怎么存怎么查」,sync-server 管「经验怎么进来」**;中间隔着 memory system 的接口层。

## 3. worker:一个数据来源一个

**worker = adapter + 监听方式 + 推送循环**,一个来源一个,声明式注册:

```
worker 契约(每个 worker 实现四件事):
  listen()         怎么发现「有新数据了」——fs watch / 定时 poll / webhook,来源自己选
  pull(cursor)     从游标之后增量读上游的私有格式(probe sha → read_after)
  normalize(raw)   ★ worker 的核心加工:把上游私有格式整理成标准 session 格式
                     (统一的 session / rounds 形状:index、role、text、时间戳、来源元数据)
  push(session)    发进 ingest 接口(幂等:乐观并发冲突就按服务端游标重拉重试)
```

**normalize 是 worker 存在的核心理由**:每个来源的原始格式都不一样(claude-code 的 jsonl 结构、codex 的会话文件、将来的浏览器 / 聊天记录更是千奇百怪)——**上游的花样死在 worker 这一层**,ingest 接口只认一种标准格式。加来源不会污染 memory 侧的 schema:标准格式不动,新来源自己写自己的 normalize。

- **现有三个 adapter 原地变身三个 worker**:claude-code / codex / openclaw(probe / list_sources / read_after 的 adapter 契约保留,套上 worker 的生命周期);
- **worker 之间完全隔离**:各自的队列、退避重试、熔断——一个来源坏了(格式变更、目录消失)只熄它自己的灯,别的照跑;
- **加来源 = 加一个 worker**:配置里声明(来源类型 + 路径 / 凭据 + 节奏),不改核心;
- **冷扫与增量同一条路**:保留现在的好设计——backfill 就是「对 list_sources() 逐个跑一遍同步」,live 事件就是「对被触碰的源跑同一段」,**判定新数据的逻辑只有一处**。

## 4. 边界

- **只做格式加工,不做语义加工**:worker 的加工止于 **normalize**(私有格式 → 标准 session 格式,内容如实、不增删语义);**不结晶、不治理、不总结**——那是 memory system / harness 的活([README](README.md) 的分工);
- **不碰 seekbase**:永远只走 ingest 接口,不知道底下是 DuckDB 还是别的——接口层是它与 memory 的唯一接触面;
- **单向**:外部 → memory。它不替 executor 拉召回(那是宿主/嵌入契约的事);
- **不认识 card**:它的世界里只有「来源、游标、rounds」。

## 5. 待定

- **进程模型**:单进程内多 worker(asyncio task 群,当前形态平移)还是 per-worker 子进程(隔离更硬、开销更大)——先单进程多 task,留出拆分口;
- **传输**:本地形态走 localhost HTTP 还是 UDS;云端形态的认证(token)与压缩、断线缓冲(worker 本地攒批,memory 不在也不丢);
- **worker 配置格式**:声明文件(哪些来源开、路径、poll 间隔)+ CLI(`sync-server status` / 单源触发);
- **backpressure**:上游洪峰(一次导入几百个 session)时对 ingest 的限流;
- **迁移**:`sync.db` 原样带走;`memory.talk sync` 命令变成对 sync-server 的控制面;主进程删掉 watcher 后 `/v3/sync/status` 的去留。

## 与其他 v5 文档的关系

- [README.md](README.md):sync-server 是 memory system **外**的平级基础服务——system 管能力,sync-server 管「经验进门」;
- [seekbase.md](seekbase.md):平级关系——经验经 ingest 接口落库后才见 seekbase;sync-server 自己的 checkpoint 不放 seekbase(connector 状态,跟着服务走);
- [memory-harness.md](memory-harness.md):harness 的「摄入(Ingest)」消费的就是 sync-server 搬进来的数据 session;两者以「数据 session 落库」为交接点(harness 不管怎么搬来的)。
