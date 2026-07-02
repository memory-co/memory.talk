# memory harness — 核心设计:双引擎、窄工具面、session 自进化(v5 设计)

> **状态:设计中。** 本篇给 [README §5 的北极星](README.md)定**核心机制**:memory harness 的引擎形态(**CC 引擎 + 自研 Lua 引擎**)、能力面(**只有 memory system 的 interface**)、以及 session 的处理(**不硬切分,让 harness 自进化出来**)。落地顺序仍按 [README §7](README.md)(system 先行);本篇先把 harness 定形。

相关:
- v5 立意(harness 为何存在、与 executor 的两分): [README.md](README.md)
- 查询接口(本篇唯一放行的能力面): [query-frame.md](query-frame.md)
- 数据层(引擎状态与自进化代码的落点): [seekbase.md](seekbase.md)

---

## 0. 先澄清一个词:两种「session」

本篇会反复说 session,**必须先分清两个完全不同的概念**:

| | **数据 session**(机器上已有的) | **harness session**(本篇讨论的) |
|---|---|---|
| 是什么 | executor 跑出来的**对话历史**(`sessions` / `rounds` 表,`sess_…`) | harness **自己运行时**的上下文分段方式 |
| 属于 | **数据**——被摄入、被 mark、被抽卡的**对象** | **运行时结构**——harness 工作时的「一段」怎么算 |
| 本篇立场 | 不动,照旧是记忆的原料 | **不预制**:CC 引擎单 session、Lua 引擎无 session,让 harness 自己进化出分段(§4) |

下文凡不加限定的「session」都指 **harness session**;数据 session 一律写全称。

---

## 1. 双引擎:CC(租)与 Lua(自研)

memory harness 的**循环体**(谁在跑「摄入 → 提炼 → 治理 → 巩固」)有两个引擎形态,**同一套能力面**(§2),可先后也可并存:

| | **CC 引擎**(先做) | **自研 Lua 引擎**(后做) |
|---|---|---|
| loop 从哪来 | **租** CC 的 agentic loop(模型 + 工具调用循环现成) | **自写**:harness 循环用 **Lua** 写,跑在沙箱 VM 里 |
| 智能从哪来 | CC 里的模型 | 注入的 `llm()` 接口(判断类工作照样调模型——上限仍是模型上限,守 [README §2](README.md)) |
| 能力面 | **剥掉基础工具**(WebSearch / 文件读写 / Bash 全去掉),只挂 memory interface(§2) | 沙箱**只注入** memory interface + `llm()`,天生摸不到别的 |
| session | **单一 harness session**(§4) | **没有 session**(§4) |
| 自进化 | 否(loop 是租的,改不了) | **是**——引擎可以改写自己的 Lua(§3) |

**为什么先 CC**:loop、模型调度、重试、上下文管理全是现成的,把「memory harness 作为一个专职 agent」最快跑起来——注意这跟 README §7 的「CC 当宿主」是**两回事**:宿主场景是 *executor CC* 顺手驱动 memory system(记忆是副业);**CC 引擎场景是一个专职 CC 实例,它的全部世界就是记忆**(记忆是唯一职业)。

**为什么自研要用 Lua**:因为要**自进化**。引擎要能改写自己的循环逻辑,就必须保证「它改了自己之后,仍然摸不到任何别的东西」——Lua 正是为此而选:

- **嵌入式、极小、无 ambient authority**:一个干净的 Lua VM 里**什么都没有**(没有 fs / net / os),能力全靠宿主注入——注入什么,它的世界就是什么。沙箱不是加锁,是**从没有钥匙**;
- 解释执行、代码即数据:引擎读自己的源码、生成新版、加载运行,天然顺手;
- 单文件可嵌进 daemon,不引庞大运行时。

## 2. 能力面:只有 interface,别的一概没有

**两个引擎共用同一条纪律:能触到的只有 memory system 的 interface。**

```
可用:
  query(sql)            ← query-frame 的只读 SQL(含 semantic() / as-of)
  受治理写动作           ← mark 提交 / position / review / link / merge / decay …(system 的动作集)
  llm(prompt)           ← 判断类工作调模型(Lua 引擎;CC 引擎自带)
没有:
  WebSearch / WebFetch  ← 记忆管理不需要外部世界;需要的知识在模型和 corpus 里
  文件读写 / Bash        ← 摸不到宿主机;文件镜像是 seekbase 的内政,不是 harness 的手
  任意 HTTP / MCP       ← 同上
```

为什么收这么窄:

1. **职责对齐**:memory harness 的唯一职责是记忆([README §5](README.md));它的动作全落在 corpus 上,工具面就该等于「对 corpus 能做的事」。
2. **自进化的安全前提**(§3):Lua 引擎会改写自己——能力面窄到「只有 memory interface」,进化再野也只能在记忆的世界里折腾,**出不了这个圈**。CC 引擎虽不自进化,同一纪律保证两个引擎行为可互换、可对照。
3. **可审计**:一切动作都是 memory 动作 → 全部过受治理写路径 → 全部有记录,时光机(seekbase §7)能回放「它当时对 corpus 做了什么」。

## 3. 自进化:引擎改写自己,但只能在沙箱里

自研引擎的核心赌注:**harness 的循环策略(何时摄入、先治理什么、巩固的节奏)不该由人一次性设计死,该让它自己长**。机制:

- **引擎代码是数据**:harness 的 Lua 源码本身**存进 seekbase**(一张 `engine_versions` 表 + 文件镜像)——版本化、可 grep、**时光机可回放它的进化史**;
- **自改 = 一次受治理的写**:引擎提出新版本(`llm()` 辅助生成)→ 落表(append-only,新版本号)→ **影子运行**(新旧并跑对照,或在 as-of 快照上干跑)→ 达标才切换,坏了回滚到上一版本号;
- **沙箱保证进化不越界**:改的是 Lua,跑在同一个「只注入 interface」的 VM 里——它可以把自己改得更聪明,**改不出新的能力面**(权限不是代码给的,是宿主注入的);
- **看门狗在 VM 外**:预算(每轮 token / 动作数上限)、超时、异常率熔断——这些护栏是宿主(daemon)的,引擎自己碰不到。

> 这正是 [README §9「自主下的治理」](README.md)的落点:v4 的纪律是「别让 AI 自评惊讶,交给检索」;这里的纪律是「**别让 harness 自评进化成功,交给影子对照 + 可回滚**」。

## 4. session:不硬切分,让 harness 自己进化出来

(再强调一次:这里说的是 **harness session**,不是数据 session——见 §0。)

- **CC 引擎:永远只有一个 harness session。** 不按任务开新会话、不搞多会话并行——一个专职实例、一条长会话,上下文靠 CC 自身的压缩续命。
- **Lua 引擎:干脆没有 session 这个概念。** 引擎就是一个循环;它的全部持久状态都在记忆库里(corpus + 自己的工作表),没有「会话」这层运行时结构。

**为什么?——「什么算一段」本身就该是进化出来的,不是框架切好的。**

session 切分(什么算一段工作、上下文在哪断、断了之后带什么走)本质上**就是一个记忆管理策略**——它恰恰是 memory harness 的本职问题。如果框架先验地替它切好(每任务一 session、每天一 session),harness 就永远学不出自己的切分,只能活在人给的分段里:

- 它若需要「工作段」的概念,自然会在 corpus 里**长出自己的结构**(比如给自己建「工作日志卡」、用一张表记「本轮在忙什么」)——那是**它的** session,长在记忆里、被治理、可回放,而不是运行时的硬分段;
- 单 session(CC)/ 无 session(Lua)= 把分段的自由度**完整留给进化**;硬切分 = 把一个该学的策略焊死成框架假设。

## 5. 架构图

```
                     memory harness(本篇)
          ┌───────────────┴────────────────┐
     CC 引擎(先做)                  自研 Lua 引擎(后做)
   租 CC 的 loop;剥基础工具        Lua VM 沙箱;llm() 注入
   单一 harness session            无 session;可自进化(§3)
          └───────────────┬────────────────┘
                能力面 = memory interface(§2,唯一的手)
        query(sql,只读,query-frame)+ 受治理写动作(system)
                           │
                       seekbase(数据层;engine_versions 也在这)
```

## 6. 待定

- **CC 引擎技术形态**:headless CC / Agent SDK / 长驻进程谁合适;工具剥离怎么配(allowlist);单 session 爆 context 后的压缩策略要不要 harness 自己参与。
- **Lua 细节**:5.4 还是 Luau;VM 配额(内存 / 指令数);`llm()` 的模型路由与预算。
- **自进化的验收**:影子运行比什么指标(README §9 的记忆质量指标是前置依赖);切换 / 回滚谁拍板(初期 human-in-loop,达标后自动?)。
- **触发**:两个引擎被什么唤醒(数据 session 落库事件 / 定时 / 手动),预算怎么给。
- **两引擎并存期**:CC 引擎与 Lua 引擎同时在跑时怎么分工(按动作类型?按 corpus 分片?),写冲突靠受治理写路径的幂等性够不够。

## 与其他 v5 文档的关系

- [README.md](README.md):本篇是 §5 北极星的机制展开;「本版不实现」的节奏不变,设计先立。
- [query-frame.md](query-frame.md):§2 能力面的读侧就是它;harness 的一切「问」都走这份 SQL frame。
- [seekbase.md](seekbase.md):harness 的动作最终都是 seekbase 读写;引擎自身代码(`engine_versions`)、工作状态也落在它上面,时光机顺带覆盖「harness 的进化史」。
