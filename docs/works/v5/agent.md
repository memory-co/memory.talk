# agent — 实例化的记忆管家:harness 底座、独立 mind、session 自进化(v5 设计)

> **状态:设计中。** [README §5 北极星](README.md)的落地实体叫 **agent**:一个**实例化**的记忆管家。每个 agent = `name` + **`harness` 字段**(底座:`claude-code` / `codex` / `lua` 自进化)+ **一个独立的 mind 库** + 常驻 server(可对话)。**reality 只有一份(共享经验),mind 每个 agent 一个(各自的信念)**。

相关:
- v5 立意(为什么记忆管理要有自己的 loop): [README.md](README.md)
- 每实例一个的信念库: [mind-data.md](mind-data.md) · 共享的经验库: [reality-data.md](reality-data.md)
- server 契约(chat / status,harness 无关的同一套): [../../api/v5/agent.md](../../api/v5/agent.md) · CLI: [../../cli/v5/agent.md](../../cli/v5/agent.md)

---

## 0. 词汇表(先钉死)

| 词 | 是什么 |
|---|---|
| **agent** | 实例化的记忆管家:`name` + `harness` + 自己的 mind 库 + 常驻 server。可同时存在多个 |
| **harness** | agent 的一个**字段**:loop 跑在哪个底座上——`claude-code` / `codex`(租现成 executor harness)或 `lua`(自研自进化) |
| **harness session** | 底座运行时的上下文分段(≠ 数据 session,见 §4) |
| **数据 session** | reality 库里的对话历史(`sess_…`),被摄入、被结晶的**对象** |

## 1. 实例化:一个 reality,多个 mind

**agent 是实例,不是单例**:

```bash
memory.talk agent create curator --harness claude-code
memory.talk agent create sandbox --harness lua
```

- **每个 agent 一个独立的 mind 库**(自己的 seekbase 实例):信念、proofs、engine_versions(lua)全在自己库里——**信念有主人**:谁结晶的、谁治理、谁负责;
- **reality 全局一份、所有 agent 共享(只读)**:经验是客观事实,不因观察者而异——**事实共享,判断各自长**;
- 实例间互不可见(mind 之间不互读;交流走各自的 chat,不预制信念交换接口);
- **实例化白送两样**:**影子对照**(candidate 引擎 = 起一个影子 agent,同一 reality 上跑,比 [metrics](metrics.md))和**多信念并存**(不同 harness / 不同策略的 agent 养各自的图,优胜劣汰)。

## 2. harness 字段:三种底座,同一能力面

| `harness` | loop 从哪来 | 智能 | 自进化 | harness session |
|---|---|---|---|---|
| `claude-code` | 租 CC 的 agentic loop(剥掉 WebSearch / 文件读写 / Bash) | CC 内的模型 | 否 | **单一**长会话 |
| `codex` | 租 Codex 的 loop(同样剥基础工具) | Codex 内的模型 | 否 | **单一**长会话 |
| `lua` | 自研:Lua 循环跑在沙箱 VM | 注入的 `llm()` | **是**(§3) | **无** |

- **能力面 harness 无关**(§2.5):换底座不换契约——server API(chat / status)、动作集、指标全一样;
- **为什么租得动**:claude-code / codex 这类 executor harness 的 loop、模型调度、上下文管理是现成的——工具面剥到只剩 memory interface,它就是合格的记忆管家底座;
- **为什么自研用 Lua**:要**自进化**。干净 Lua VM 无 ambient authority(没有 fs / net / os),能力全靠注入——沙箱不是加锁,是**从没有钥匙**;解释执行、代码即数据,引擎改写自己天然顺手。

### 2.5 能力面:只有 memory interface

```
可用(对自己的 mind 库):
  query(sql)            ← 只读 SQL(agent mind;含 semantic() / as-of)
  受治理写动作           ← card(撞库判新)/ position / review / link / merge / decay …
可用(对共享 reality):
  query(sql)            ← 只读(经验是证据,谁都改不了)
  llm(prompt)           ← lua harness 注入;claude-code / codex 自带
没有:
  WebSearch / 文件读写 / Bash / 任意 HTTP   ← 记忆管家的世界里只有记忆
```

收窄的理由不变:职责对齐(动作 = 对 corpus 能做的事)、自进化的安全前提(§3)、可审计(一切动作过受治理写路径,时光机可回放)。

## 3. 自进化(lua harness 独有)

- **引擎代码是数据**:Lua 源码存进**该 agent 自己的 mind 库**(`engine_versions` 表)——版本化、可 grep、时光机可回放进化史;
- **自改 = 受治理的写**:新版本 append-only 落表 → **影子对照**(起一个影子 agent 在同一 reality 上干跑,比 [metrics §3](metrics.md) 的护栏组 + 目标线)→ 达标才切换,坏了回滚版本号;
- **沙箱保证进化不越界**:改的是 Lua,跑在同一个「只注入 interface」的 VM 里——能改得更聪明,**改不出新的能力面**;
- **看门狗在 VM 外**:预算 / 超时 / 异常率熔断是宿主(daemon)的,引擎碰不到。

> 纪律同 v4 一脉:「别让 AI 自评惊讶,交给检索」→「别让 agent 自评进化成功,交给影子对照 + 可回滚」。

## 4. harness session:不硬切分,让它自己长

(说的是 **harness session**,不是数据 session——§0。)

- `claude-code` / `codex`:**永远单一会话**(一个实例一条长会话,上下文靠底座自己压缩);
- `lua`:**没有 session 这个概念**(循环 + 状态全在 mind 库里);
- **为什么**:「什么算一段」本身就是记忆管理策略——框架先验切好,agent 就永远学不出自己的分段;它需要「工作段」会在自己的 mind 里长出结构(工作日志卡 / 自己的表),被治理、可回放。conversations 的 `conv_id` 同理只是传输分组([reality-data](reality-data.md))。

## 5. 运行形态:每实例一个常驻 server,可对话

agent 起来是**常驻 server**:loop 按触发跑,同时开着对话通道。**API 钉在 server 层**(chat / status,[api/v5/agent.md](../../api/v5/agent.md)):harness 只是后面的底座,换底座不换契约(底座细节只在 `status.harness` 可见,不漏进请求/响应结构)。

- **chat 是人影响记忆的正门**:你说的话是给 agent 的输入,落不落、怎么落由它经受治理写动作决定(响应 `actions[]` 带引证,可审计);人不绕过管家直接写库(所以 CLI 没有 card 写命令);
- **对话也是经验**:每条消息(双向)落 reality 的 `conversations` 表(带 `agent` 字段:谁的对话)——可回放、可语义搜、将来可作 `(type='conversation')` 证据源。

## 6. 架构图

```
                 reality(一份,共享只读;sync-server 写入)
                    ▲查              ▲查              ▲查
        ┌───────────┴────┐   ┌───────┴───────┐   ┌────┴───────────┐
        │ agent: curator │   │ agent: helper │   │ agent: sandbox │
        │ harness: cc    │   │ harness: codex│   │ harness: lua   │
        │ mind 库 ①(独立)│   │ mind 库 ②     │   │ mind 库 ③ +    │
        │ server + chat  │   │ server + chat │   │ engine_versions│
        └────────────────┘   └───────────────┘   └────────────────┘
          能力面全同:query(own mind + reality)+ 受治理写动作(own mind)
```

## 7. 待定

- **claude-code / codex harness 技术形态**:headless / SDK / 长驻进程;工具剥离配置;单会话爆 context 的压缩策略;
- **lua 细节**:5.4 还是 Luau;VM 配额;`llm()` 的模型路由与预算;
- **实例注册与进程模型**:agent registry 在哪(daemon 内 supervisor?);每实例独立端口还是控制面路由;
- **切换 / 回滚谁拍板**(自进化):初期 human-in-loop,达标后自动?
- **触发**:实例被什么唤醒(数据 session 落库事件 / 定时 / 手动 / chat),预算怎么按实例给;
- **多 agent 协作**:要不要 agent 间的信念交换——当前不预制,观察需求。

## 与其他 v5 文档的关系

- [README.md](README.md):北极星的落地实体;「本版不实现」节奏不变,设计先立;
- [mind-data.md](mind-data.md):**每 agent 一库**的信念 schema;[reality-data.md](reality-data.md):共享经验 + conversations;
- [metrics.md](metrics.md):按 agent 实例算;影子对照 = 两个实例比;
- [embed-contract.md](embed-contract.md):executor 宿主(只读+chat)vs **agent**(读+写自己的 mind)的两个 profile。
