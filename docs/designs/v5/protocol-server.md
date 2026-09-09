# protocol server —— 每个协议背后,把现场建出来的那个东西(v5 设计)

> **状态:框架稿,未实施。** 本篇只立 server 这一层的大框架:一个块由 URI 定位,URI 的协议(`://` 前面那个)决定去找哪个 server——**每个 server 自己声明它响应哪些协议**,一个 server 可以响应多个;没人声明的协议去 **default**。server 负责把那个现场建出来、交回一扇窗和一个把手。这是 shellbase 里最核心、但当时没有完全定名的那一层;v5 原生实现时把它叫 **server**。接口、注册方式、各 server 的契约后续分篇。总定位见 [README.md](README.md)。

相关:
- v5 task 树(块住在 task 的画布上;task 是现场登记的唯一权威): [task.md](task.md)
- v5 store(task 的登记是裸文件;server 不存 task 状态): [store.md](store.md)
- shellbase 块即 URI 与四分流(本篇要把「其余一切转发终端」那条显式化): [uri.md](https://github.com/memory-co/shellbase/blob/main/docs/v1/works/uri.md)
- shellbase「一扇窗 + 一个把手」与 `*muxd` 规范(server 的形状就是它): [new-interface.md](https://github.com/memory-co/shellbase/blob/main/docs/v1/new-interface.md) / [muxd-spec.md](https://github.com/memory-co/shellbase/blob/main/docs/v1/muxd-spec.md)
- v3 平台 adapter(读 Claude Code / Codex 会话记录——在 v5 归入 agent server 的把手): [../v3/sync-pipeline.md](../v3/sync-pipeline.md)

---

## 1. 一句话:协议决定找谁,server 负责建出来

task 的画布上每个块由一个 URI 定位:`codex:///workspace/proj`、`bash://`、`https://localhost:5173`、`vim:///notes.md`。URI 的**协议**(`://` 前面那个)说的是「去找谁」——**去 server 那里寻址**:每个 server 声明自己响应哪些协议(`http` server 同时接 `http` 和 `https`),没有任何 server 声明的协议(`vim://`)去 **default server**;**server** 就是认领某一类协议、并负责把这类现场**建出来或取回来**的那个东西。

```
块的 URI ──▶ 协议名 ──▶ 哪个 server 声明了它?没有就 default ──▶ server 建 / 取现场 ──▶ 交回:一扇窗 + 一个把手
                                                                      窗:给人,iframe 嵌进画布
                                                                      把手:给程序,task 层拿它观测和驱动
```

一个 server 只回答一个问题:**「给我一个这类协议的 URI,我把它变成一个活着的现场,并告诉你怎么看、怎么驱动它。」** 不多。

---

## 2. 从 shellbase 里长出来:那条「其余一切转发终端」

shellbase v1 的前端解析器只做四分流:`https` 本地服务、`https` 外链、`file://`、**其余一切转发给终端 attach 入口**。「其余一切」用一条约定处理——**scheme 名即命令名**:`codex:///proj` = `cd /proj && codex`,`vim:///notes.md` 同理,PATH 里有的命令都开箱即用,不用注册。

这条约定 v5 保留,但**收进一个明确的对象里**:它不再是 attach 端点里的隐式兜底,而是一个叫 **default** 的 server——背后就是「协议名当命令名,在 tmux 里跑」,调用方不用感知它背后是 bash。shellbase 把三件事压在了一个 attach 端点里:**这个协议归谁、怎么把现场建出来、建完交回什么**。后来 shellbase 把终端和浏览器抽成 `tmuxd` / `webmuxd`,露出了这层真正的形状——**一扇窗 + 一个把手**——但「一个协议请求到哪个组件去」这层还是没有名字,散在前端分流和后端 attach 之间。

v5 给它一个名字:**server**,寻址规则只有两条:**server 自己声明响应哪些协议**(`http.py` 声明 `http` + `https`,`codex.py` 声明 `codex`);**没人声明的协议去 default**(`vim://`、`htop://`……)。四分流不再是前端写死的四个 if,而是「每个协议请求到声明了它的 server 那里去,没有就 default」。

---

## 3. server 是什么:声明协议、幂等建现场、交回窗和把手

一个 server 有三个职责,也只有三个:

| 职责 | 意思 | 从哪来 |
|---|---|---|
| **声明响应哪些协议** | `protocols = ["http", "https"]`——一个 server 可以响应多个;`default` 不声明任何协议,专收没人要的 | shellbase 的「scheme 名即命令名」收进 default |
| **幂等地建 / 取现场** | 拿一个稳定 id 来,有就给已有的,没有就建——建和取是同一个动作,像 `tmux new -A` | `*muxd` 规范 M4 |
| **交回窗和把手** | 窗:一个人能直接打开的 HTTP 地址;把手:一个程序能驱动它的对象 | `*muxd` 规范 M1 / M2 |

外加三条它必须守的性质,全部来自 `*muxd` 规范,这里只点名:**现场活得比连接久**(关掉页面里面照常跑);**不代理那扇窗**(只报 URL,怎么摆是 task 画布的事);**状态不许撒谎**(建不出来就说建不出来,不给一个连不上的地址)。

server **不做**的事同样重要:它**不记 task**——哪个块属于哪个 task、块在画布哪个位置、什么时候开的,这些全在 task 层的裸文件里([store.md §4](store.md));server 只管「这个 id 的现场活没活着」。它**不做认知**——round 怎么标注、问题怎么建,跟它无关。

---

## 4. 请求流:一个块从 URI 到现场

1. **task 画布上放一个块**,块有一个 URI。task 层给这个块一个**稳定的会话 id**——脱离布局的那个([task.md §3](task.md)),不是格子序号。
2. **memory.talk 拿协议名去 server 那里寻址**:哪个 server 声明了它就是哪个;没人声明 → **default**。default 也建不起来(PATH 里没这个命令)→ 明确报错。
3. **server 拿(会话 id,URI)幂等地建 / 取现场**。第一次:建(起 tmux 会话、开浏览器 tab、定位目录);之后:取回同一个。
4. **server 交回窗和把手**。窗的 URL 给画布 iframe 嵌进去;把手留给 task 层——观测(这个会话跑到哪了、新的 round)、驱动(往里发一句话)、销毁(块关闭时)。
5. **task 层记登记**:会话 id ↔ URI ↔ 这个 server ↔ 现场是否活着。这份登记是 task 目录里的裸文件,是唯一权威;server 重启后,task 层拿登记去 server 那里把现场一个个取回来。

块关闭 = task 层通过把手让 server 销毁现场 + 删登记;不是只从画布上摘掉(沿用 shellbase「关闭即回收」)。

---

## 5. v5 首批 server:bash、claude、codex、kimi、http、default

一个 server 一个文件,`backend/servers/<name>.py`:

| server | 响应的协议 | 现场 | 窗 | 把手 | 蓝本 |
|---|---|---|---|---|---|
| **bash** | `bash` | tmux 会话里的 bash | ttyd 挂到 tmux 会话 | tmux:发键、抓屏 | tmuxd |
| **claude / codex / kimi** | 各自同名 | 同 bash——就是一个跑着 agent 的 tmux 会话 | 同上 | 终端把手 **+ 读它的会话记录**(round) | tmuxd + v3 adapter |
| **http** | `http`、`https` | 无(纯 iframe);将来可换成真浏览器实例 | URL 本身;本地服务经代理 | 现在为空;换成 webmuxd 后有 CDP | webmuxd |
| **default** | (不声明)没人要的都来 | tmux 会话里跑「协议名」这个命令 | 同 bash | 同 bash | shellbase 的 attach 兜底 |

要 `vim://`?什么都不用做,default 接住。要给某个协议专门的把手(比如新的 agent CLI)?加一个文件、声明协议,它就从 default 手里接过去。**别的地方一行不改**。

两点值得单说:

- **agent 类 server 和 bash 的关系**。在 shellbase 里 `codex://` 和 `bash://` 完全同构——都是「到某目录跑某命令」。v5 里它们的**现场**仍然同构(都是 tmux 会话),差别只在**把手**:memory.talk 关心 agent 的 **round**——那是 task 留下的主要痕迹、issue 的原料。所以 claude / codex / kimi = bash 的把手 **再加一项「读会话记录」**(代码上是同一个基类多一个 adapter)。v3 的平台 adapter(从 Claude Code / Codex 的记录文件里读 round)在 v5 就住在这里:它不再是「事后 sync 的读取器」,而是 agent server 把手的一部分——现场在跑,round 就在流出来。
- **http server 现在是最薄的**。shellbase v1 的浏览器面板是纯 iframe,没有把手;这不妨碍它是一个 server——窗就是那个 URL,把手为空,状态老实报「只有画面没有把手」(M13)。将来换成 webmuxd 一类的真浏览器实例,窗和把手都变强,协议不变,task 层无感——**这正是把它立成 server 的意义:实现面可以整个换掉,契约面不动**。

---

## 6. server 的形状:就是 `*muxd` 规范,不重新发明

server 这个概念**不新造一套规范**,它的形状就是 shellbase 已经写好的 `*muxd` 规范:两个端点、契约面 / 实现面分清、id 幂等、活得比连接久、库优先、可独立验证、不代理窗、失败说清楚、状态不撒谎。任何一个新 server 进来,先回答那三个问题——**窗是什么、把手是什么、哪一半是用户会直接碰到的**——答不出第三个就还没想清楚。

所以 v5 里「server」和「`*muxd` 组件」基本是一回事,只差一层:`*muxd` 说的是**一个组件自己长什么样**,server 多说了一句**它响应哪些协议、在 memory.talk 里怎么被请求到**。tmuxd、webmuxd 是现成的 `*muxd` 组件,v5 的 bash / claude / codex / kimi / http server 就包在它们外面——或者按 muxd 的说法,**它们就是 server 的实现面**。

---

## 7. 这篇有意不定的事

- **server 是进程内的库,还是独立进程**:`*muxd` 规范说库优先(`import` 就能用,HTTP 面只为独立验证)。本篇倾向照搬——server 在 memory.talk 进程内被 `import`,各自的 runtime(tmux server、chromium)是它们自己的事。真要跨机器时再议远程 server。
- ~~协议认领是注册还是约定~~:已定——**server 声明协议(注册)+ default 兜底(约定)**,两者都要,声明优先。
- ~~agent server 是不是终端 server 的一个特例~~:已定——各自独立成文件,共用 `TerminalBase` / `AgentBase` 两个基类。
- ~~纯外链、纯静态页这类没有把手的块要不要也算 server~~:已定——算,`http.py` / `https.py` 就是最薄的 server。
- **把手在 task 层暴露到什么程度**:只给观测(读 round)和销毁,还是也给驱动(往 agent 里发话)。给驱动就打开了「memory.talk 编排 agent」这扇门——那是另一个话题,本篇不碰。
- **远程现场**:块背后的现场在另一台机器上(server 在别处跑)——窗天然是 URL 所以没问题,把手怎么跨机器,留给需要时。
