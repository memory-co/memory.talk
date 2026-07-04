# embed-contract — 嵌入契约:宿主怎么用 memory system(v5 设计)

> **状态:设计中。** [README §7](README.md) 三层里的**第③层**:memory system 暴露什么、宿主怎么驱动。契约按**宿主类型**分两个 profile:**executor 宿主**(当前 = CC,只读 + 对话)与 **harness 宿主**(未来 = 专职 memory harness,读 + 受治理写)。同一套 system,两种嵌法。

相关:
- 三层落地策略(本篇是第③层): [README.md](README.md)
- 读面(query)与写面(动作)的具体契约: [../../api/v5/README.md](../../api/v5/README.md) · [../../cli/v5/README.md](../../cli/v5/README.md)
- harness 侧的能力面(harness profile 的消费者): [memory-harness.md](memory-harness.md)

---

## 1. 两个 profile:宿主是谁,决定它能干什么

| | **executor 宿主**(CC,当前) | **harness 宿主**(memory harness,未来) |
|---|---|---|
| 角色 | 干活的,顺便**用**记忆 | 养记忆的,记忆是**本职** |
| 读 | ✅ query(mind / reality) | ✅ 同左 |
| 写 mind | ❌ **没有**——想影响记忆走 `harness chat` | ✅ 受治理写动作(唯一写门) |
| 写 reality | ❌(谁都没有;只有 sync-server) | ❌ 同左 |
| 交经验 | **零动作**(§4:sync-server 的 worker 侦听,宿主不用调任何东西) | 不适用(它消费经验,不产生) |

**executor 宿主没有写权是契约的立场,不是缺功能**:executor 的判断是任务驱动的顺手判断,直接落库会绕开治理;它对记忆的影响一律**说给管家**(`harness chat`),由 harness 决定落不落、怎么落。

## 2. 契约面:就四个通道

宿主(不管哪个 profile)接触 memory system 的通道只有:

```
① query    mind / reality 两库各一个只读门(CLI 命令 或 POST /v5/query)
② chat     harness 对话通道(人/宿主影响记忆的正门)
③ status   sync status(经验进没进来)+ harness status(管家在忙什么)
④ actions  受治理写动作(仅 harness profile;api/v5/cards.md)
```

没有第五个:不碰 seekbase、不碰 ingest、没有绕过 query 的专用读端点。**契约小,宿主换起来才便宜**——这就是「同一套 system 嵌进任何 harness」的兑现方式。

## 3. CC 宿主怎么嵌:三件套分工

| 机制 | 承担什么 | 用哪个通道 |
|---|---|---|
| **hooks** | **无意识召回**:session 开场 / 提问时,把相关记忆注入 context(§5) | ① query(预制 SQL) |
| **skills / slash** | **有意识检索**:CC 干活中主动查(`/mem <问题>` → 包一条 `memory.talk mind …`);以及把「这条要记 / 这条不对」转发给管家 | ① query + ② chat |
| **CLAUDE.md** | **教 CC 什么时候用**:何时主动查、何时该跟 harness 说一声——行为指引,不是新机制 | — |

CC 宿主全程是 **CLI 的消费者**(`memory.talk mind/reality/harness/sync`),不直连 HTTP——CLI 就是嵌入面的 SDK。

## 4. 交经验:宿主零动作(契约里最省的一条)

executor **不需要「提交经验」这个调用**:CC 把 session 写到自己的目录,[sync-server](sync-server.md) 的 worker 侦听、normalize、推 ingest——**宿主感知不到摄入的存在**。

这是设计选择,不是省略:让「交经验」成为 executor 的义务(要装 SDK、要在对的时机调对的接口),嵌入成本立刻变高、还会漏(崩溃的 session 就交不上);被动侦听则**宿主装完即忘**,经验一条不漏。新 executor 想接入 = 给 sync-server 加一个 worker,executor 自己零改动。

## 5. 召回:两种,都不加新端点

- **无意识召回**(hook 注入):session 开场 / 用户提问 → hook 拿 prompt 文本跑一条**预制 SQL**(`semantic('cards', <prompt>)` join `v_card_best`,top-k 带 credence 门槛)→ 结果作为 context 注入。预制 SQL 是**宿主侧配置**(hook 脚本里的一段 SQL),不是 system 的新端点——调多了口味(门槛 / k / 过滤)改宿主自己的 SQL 就行。
- **有意识检索**(CC 主动):干活中觉得「这事以前见过」→ `/mem` 或直接 `memory.talk mind "…"`。

v4 的 `recall` 命令 / 端点不回归:两种召回都是 query 上的一条 SQL,差别只在**谁触发**(hook vs CC 自己)。

## 6. 待定

- **hook 的预制 SQL 模板**:开场注入 vs 每问注入的默认策略;prompt → semantic 查询文本的裁剪(长 prompt 摘要?);注入格式(markdown 块的形状);
- **chat 转发的形态**:skill 里「记一下 X」转发给 `harness chat` 时,要不要带上当前 session 的定位(让 harness 有 grounding 可查);
- **harness profile 的动作认证**:本地 loopback 够;云端形态动作 token 与查询 token 分权(api/README 已留);
- **多 executor 并存**:多个 CC(或别的 executor)同时嵌——query/chat 天然多客户端,唯一要防的是两个「自称 harness」抢写权(动作端 token 单发?)。

## 与其他 v5 文档的关系

- [README.md](README.md):第③层落定,system 三层齐(seekbase → 能力 → 本篇);
- [memory-harness.md](memory-harness.md):harness profile 的消费者——它的能力面(§2)就是本契约的 ①+④;
- [sync-server.md](sync-server.md):§4「零动作交经验」的另一半——它监听,宿主免责。
