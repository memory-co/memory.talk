# protocol server —— 每个协议背后,把现场建出来的那个东西(v5 设计)

> **状态:定稿,已有实现;读 agent 记录那部分按 [work-node.md](work-node.md) 改(未实施)。** 本篇立 server 这一层的框架:一个块由 URI 定位,URI 的协议(`://` 前面那个)决定去找哪个 server——**每个 server 自己声明它响应哪些协议**,一个 server 可以响应多个;没人声明的协议去 **default**。server 负责把那个现场建出来、交回一扇窗和一个把手。这是 shellbase 里最核心、但当时没有完全定名的那一层;v5 原生实现时把它叫 **server**。接口、注册方式、各 server 的契约后续分篇。总定位见 [README.md](README.md)。

相关:
- v5 work 树(块住在 work 里,摆在它的某一列;work 是现场登记的唯一权威): [work.md](work.md)
- v5 work 存储(work 的登记是 `works.db` 里 `worklets` 表的一行;server 不存 work 状态): [work-store.md](work-store.md)
- shellbase 块即 URI 与四分流(本篇要把「其余一切转发终端」那条显式化): [uri.md](https://github.com/memory-co/shellbase/blob/main/docs/v1/works/uri.md)
- shellbase「一扇窗 + 一个把手」与 `*muxd` 规范(server 的形状就是它): [new-interface.md](https://github.com/memory-co/shellbase/blob/main/docs/v1/new-interface.md) / [muxd-spec.md](https://github.com/memory-co/shellbase/blob/main/docs/v1/muxd-spec.md)
- v3 平台 adapter(读 Claude Code / Codex 会话记录——在 v5 搬进节点的上报任务,见 [work-node.md](work-node.md)): [../v3/sync-pipeline.md](../v3/sync-pipeline.md)
- 每个 server 的 input / output 口子: [work-server-io.md](work-server-io.md)

---

## 1. 一句话:协议决定找谁,server 负责建出来

work 里每个块由一个 URI 定位:`codex:///workspace/proj`、`bash://`、`https://localhost:5173`、`vim:///notes.md`。URI 的**协议**(`://` 前面那个)说的是「去找谁」——**去 server 那里寻址**:每个 server 声明自己响应哪些协议(`http` server 同时接 `http` 和 `https`),没有任何 server 声明的协议(`vim://`)去 **default server**;**server** 就是认领某一类协议、并负责把这类现场**建出来或取回来**的那个东西。

```
块的 URI ──▶ 协议名 ──▶ 哪个 server 声明了它?没有就 default ──▶ server 建 / 取现场 ──▶ 交回:一扇窗 + 一个把手
                                                                      窗:给人,iframe 嵌进页面
                                                                      把手:给程序,work 层拿它驱动(观测由节点往上推)
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
| **幂等地建 / 取现场** | 拿一个稳定 id 来,有就给已有的,没有就建——建和取是同一个动作,像 `tmux new -A` | `*muxd` 规范 M4;实现上就是 `Tmuxd.session(id=…)` |
| **交回窗和把手** | 窗:一个人能直接打开的 HTTP 地址;把手:一个程序能驱动它的对象 | `*muxd` 规范 M1 / M2;实现上就是 `Session.url` 和 `Session` 本身 |

外加三条它必须守的性质,全部来自 `*muxd` 规范,这里只点名:**现场活得比连接久**(关掉页面里面照常跑);**不代理那扇窗**(只报 URL,摆在哪是 work 的列的事);**状态不许撒谎**(建不出来就说建不出来,不给一个连不上的地址)。

server **不做**的事同样重要:它**不记 work**——哪个块属于哪个 work、块在哪一列哪个位置、什么时候开的,这些全在 work 层的 `works.db` 里(`worklets` 表,[work-store.md §3](work-store.md));server 只管「这个 id 的现场活没活着」。它**不做认知**——消息怎么标注、问题怎么建,跟它无关。

---

## 4. 请求流:一个块从 URI 到现场

1. **work 里放一个块**,块有一个 URI。work 层给这个块一个**稳定的工作单元 id**——脱离位置的那个([work.md §3](work.md)),不是块序号。
2. **memory.talk 拿协议名去 server 那里寻址**:哪个 server 声明了它就是哪个;没人声明 → **default**。default 也建不起来(PATH 里没这个命令)→ 明确报错。
3. **server 拿(工作单元 id,URI)幂等地建 / 取现场**。第一次:建(起 tmux 会话、开浏览器 tab、定位目录);之后:取回同一个。
4. **server 交回窗和把手**。窗的 URL 给前端 iframe 嵌进去;把手留给 work 层——驱动(往里发一句话)、销毁(块关闭时)。观测不走把手:现场在跑,现场所在机器上的节点读它的会话记录、收 hooks,往中心推([work-node.md](work-node.md))。
5. **work 层记登记**:工作单元 id ↔ URI ↔ 这个 server ↔ 现场是否活着。这份登记是 `works.db` 里 `worklets` 表的一行([work-store.md §3](work-store.md)),是唯一权威;server 重启后,work 层拿登记去 server 那里把现场一个个取回来。

块关闭 = work 层通过把手让 server 销毁现场 + 删登记;不是只从列里摘掉(沿用 shellbase「关闭即回收」)。

---

## 5. v5 首批 server:bash、claude、codex、kimi、http、default

一个 server 一个文件,`memorytalk/backend/work_servers/<name>.py`:

| server | 响应的协议 | 现场 | 窗 | 把手 | 实现面 |
|---|---|---|---|---|---|
| **bash** | `bash` | tmux 会话里的 bash | ttyd(tmuxd 自带)挂到 tmux 会话 | `send` | **tmuxd** |
| **claude / codex / kimi** | 各自同名 | 同 bash——就是一个跑着 agent 的 tmux 会话 | 同上 | `send`;开现场时另外定下会话 id、注入 hooks,由节点读会话记录、推成会话 / 轮次 / 工具段和消息点(`output.messages`) | **tmuxd** + 节点里的 adapter |
| **http** | `http`、`https` | 无(纯 iframe);将来换成真浏览器实例 | URL 本身 | 现在为空;换成 webmuxd 后有 CDP | 将来 **webmuxd**(先不做) |
| **default** | (不声明)没人要的都来 | tmux 会话里跑「协议名」这个命令 | 同 bash | 同 bash | **tmuxd** |

要 `vim://`?什么都不用做,default 接住。要给某个协议专门的把手(比如新的 agent CLI)?加一个文件、声明协议,它就从 default 手里接过去。**别的地方一行不改**。

两点值得单说:

- **agent 类 server 和 bash 的关系**。在 shellbase 里 `codex://` 和 `bash://` 完全同构——都是「到某目录跑某命令」。v5 里它们的**现场**仍然同构(都是 tmux 会话),差别在两处。**开现场时多做一点**:定下 agent 的会话 id(Claude Code 的 `--session-id`)、注入 hooks,这样记录是谁的不用事后猜。**留下的记录**:memory.talk 关心 agent 说了什么——那是 work 留下的主要痕迹、issue 的原料。读记录的不是把手,而是现场所在机器上的节点([work-node.md](work-node.md)):v3 的平台 adapter(从 Claude Code / Codex 的记录文件里读对话)在 v5 住在节点的上报任务里,它不再是「事后 sync 的读取器」,也不是「有人看才去拉」——现场在跑,会话、轮次、工具调用和每条消息就推进 trace([work-trace.md §2](work-trace.md))。
- **http server 现在是最薄的**。shellbase v1 的浏览器面板是纯 iframe,没有把手;这不妨碍它是一个 server——窗就是那个 URL,把手为空,状态老实报「只有画面没有把手」(M13)。将来换成 webmuxd 一类的真浏览器实例,窗和把手都变强,协议不变,work 层无感——**这正是把它立成 server 的意义:实现面可以整个换掉,契约面不动**。

---

## 6. server 的形状:就是 `*muxd` 规范——所以直接用 `*muxd` 库,不自己实现

server 这个概念**不新造一套规范**,它的形状就是 shellbase 已经写好的 `*muxd` 规范:两个端点、契约面 / 实现面分清、id 幂等、活得比连接久、库优先、可独立验证、不代理窗、失败说清楚、状态不撒谎。任何一个新 server 进来,先回答那三个问题——**窗是什么、把手是什么、哪一半是用户会直接碰到的**——答不出第三个就还没想清楚。

「形状是 `*muxd` 规范」这句话只有一种兑现方式:**server 的实现面就是一个 `*muxd` 库**。自己再写一遍 `tmux new-session` / `has-session` / `kill-session`,然后说「照 tmuxd 的规范」,是空话——规范里的每一条(id 幂等、ttyd 那扇窗、活得比连接久、不碰用户自己的 tmux、失败说清楚)都是库里已经做完的事,自己实现一遍只会做出一个更差的、没被验证过的 tmuxd。所以:

- **终端这一族(bash / claude / codex / kimi / default)全部跑在 [tmuxd](https://github.com/memory-co/tmuxd)(pip `tmuxd`)上。** memory.talk 进程里持有一个 `Tmuxd` 实例(自己的 socket、自己的 ttyd、自己的 state 目录,都在 `~/.memory.talk/tmuxd/` 下),每个终端类 server 拿着它:建 / 取现场 = `t.session(id=worklet_id, cwd=…, cmd=…)`;窗 = `s.url`(ttyd 跟着 tmuxd 自带,**不再需要自己配一个 ttyd**);把手 = `s`(`alive` / `send` / `send_key` / `kill`)。server 自己只剩两件事:**决定 cwd 和命令**(协议名当命令名、path 当工作目录),以及 agent 类**开现场时多做一点**——定下会话 id、注入 hooks(读记录的是节点,不是 server)。
- **tmuxd 只写不读,所以 server 也只写不读。** 原来的 `capture`(抓屏)去掉:读终端归人(打开那扇窗),不归 API。agent 的对话不是抓屏,是读平台自己落的记录文件和 hooks,那是节点的事。
- **http server 将来跑在 webmuxd 上。** 浏览器那一块比终端复杂(真浏览器实例、CDP 把手),先不做;现在的 http server 就是最薄的那个——窗 = URL,把手为空。换成 webmuxd 时协议不变,work 层无感。

所以 v5 里「server」和「`*muxd` 组件」的关系是:`*muxd` 库是**实现面**,server 是包在外面的**契约面**——多说一句它响应哪些协议、在 memory.talk 里怎么被请求到,再多一点 memory.talk 自己关心的事(开现场时定下 agent 的身份,让节点读得准)。

窗的地址由 tmuxd 决定:ttyd 听 state 目录里的 unix socket,`tmuxd.asgi()` 挂在 memory.talk 主路由的 `/surface/tmuxd`,窗 = `/surface/tmuxd/?arg=<worklet_id>`,和 API 同一个端口、同一扇门(§7)。再往外的反代归网关那一层,不归 server。

---

## 7. 窗挂到主路由上:ttyd 走 unix socket,tmuxd 交出一个 ASGI handle(已实现,tmuxd 3.0)

### 7.1 当时的问题(tmuxd 2.x)

`Tmuxd(...)` 在 `WorkServerService.__init__` 里被实例化,顺手拉起 ttyd 听一个 TCP 端口(`MEMORY_TALK_TMUXD_PORT`);`s.url` 是 `http://<host>:<port>/?arg=<id>`,前端 iframe 直接连过去。于是**窗在 memory.talk 的门外**:

- 多一个端口要开防火墙(2026-09-28 那次「8091 没了」:ttyd 好好的,是云上防火墙只放了 8090);
- 多一套认证:ttyd 的 basic auth(`tmuxd:<token>`,明文、全员共用),和 memory.talk 的登录([auth.md](auth.md))毫无关系——拿到这个 token 的人绕过登录直接进 shell;
- 四个环境变量(`_PORT` / `_BIND` / `_TOKEN` / `_URL_HOST`)只为让浏览器找得到这扇窗。

### 7.2 目标形状

```
浏览器 ──https──▶ memory.talk(uvicorn,一个端口)
                  ├─ /api/...  FastAPI 路由(Bearer 门)
                  ├─ /surface/tmuxd/...  ──▶ t.asgi() ──UDS──▶ ttyd -i <state>/ttyd.sock -b /surface/tmuxd
                  └─ /         前端静态资源
```

窗仍然是 ttyd 那一页,只是**从 memory.talk 同一个端口、同一扇门进去**。tmuxd 交出来的 handle 是一个 **ASGI app**,memory.talk 一行 `app.mount("/surface/tmuxd", tmuxd.asgi())` 挂上。

**`/surface` 是所有「窗」的命名空间**:终端在 `/surface/tmuxd`,以后浏览器(webmuxd)挂 `/surface/webmuxd`,同一个 cookie、同一条门规则(auth.md §1)。前缀定在 `gateway.SURFACE_PATH`,`main.py` 只把它交给 `WorkServerService`;下面有哪些窗、各叫什么由 service 自己定,`surfaces()` 交回「(挂载点, ASGI app)」清单,`main.py` 逐个 mount。挂载点就是各实例的 `base_path`,只算一次。加 webmuxd = service 里多一个实例、`surfaces()` 多一行,`main.py` / 门 / cookie 不动。

### 7.3 为什么是 ASGI,而不是 FastAPI router

ASGI 是调用约定(`async def app(scope, receive, send)`),不是框架:FastAPI / Starlette / Litestar / Quart 都能 mount。tmuxd 已有的 `tmuxd.server.router` 是 FastAPI 的 `APIRouter`,那是**控制 API**(JSON 进 JSON 出,给 CLI 用),和这里的**窗流量**是两件事,不合并。依赖分层:

| 层 | 依赖 |
|---|---|
| `import tmuxd`(核心) | 无,同现在 |
| `tmuxd.asgi`(extra `tmuxd[asgi]`) | asyncio + `websockets`(只用来连 ttyd 那一侧;uvicorn standard 已带) |
| `tmuxd.server`(extra `tmuxd[server]`) | FastAPI,不变 |
| memory.talk | 一行 mount + 一个 `authorize` 函数 |

唯一挂不上的是 WSGI(Flask / 同步 Django)——WSGI 没有 WebSocket,谁实现都一样。

### 7.4 和 `*muxd` 规范 M11「不代理那扇窗」的关系

M11 说组件只报 URL,「要不要套一层网关是上层的事」。这条不破:

- **核心只加两个部署参数,仍然只报 URL**:`listen="unix"`(ttyd `-i <state_dir>/ttyd.sock`,0600)和 `base_path="/surface/tmuxd"`(ttyd `-b`,它自己的页面、`/token`、`/ws` 都带这个前缀)。`s.url` 变成相对的 `/surface/tmuxd/?arg=<id>`。没有自造路径、没有 302、不解析 ttyd 协议。
- **转发器是上层工具,放在 extra 里**:`t.asgi()` 只做字节搬运——HTTP 原样转到 UDS;WebSocket 两侧各一个 task 对拷帧,透传 `tty` 子协议,不看帧内容。它是 tmuxd 替上层备好的网关零件,不是核心行为;不装 extra、不 mount,tmuxd 和今天一样。
- 如果 tmuxd 那边坚持核心之外也不收,这段转发器原样落在 memory.talk 里(`services/work_servers/tty_proxy.py`),接口不变。

### 7.5 tmuxd 这边(3.0 已做)

- `Tmuxd(listen="unix" | ("tcp", port), base_path=None, ...)`:默认 unix;TCP 模式留给 CLI / 单独使用。unix 模式下 bind / token 不再需要(socket 文件权限就是门),`bind=0.0.0.0` 必须带 token 的检查只在 TCP 模式生效。
- ttyd 记录从 `ttyd-<port>.json` 改成按监听地址命名(unix 模式 `ttyd-unix.json`),`ensure()` 认领旧 ttyd 也按 socket 路径认。
- `url_for(sid)`:unix 模式返回 `<base_path>/?arg=<sid>`(相对地址);TCP 模式同现在。
- `t.asgi(authorize=None)`:`authorize(scope) -> bool | Awaitable[bool]`,为假回 401/403(WebSocket 用 close 1008)。tmuxd 不懂谁是谁,**鉴权全在钩子里**。
- 生命周期**仍归 `Tmuxd`**:ttyd 在 `__init__` 起、`close()` 收;ASGI app 不管 ttyd 死活(也避开 Starlette mount 子 app 收不到 lifespan 的坑)。

### 7.6 memory.talk 这边

- `config.py`:删掉 `MEMORY_TALK_TMUXD_PORT` / `_BIND` / `_TOKEN` / `_URL_HOST`;`WorkServerService(runtime, surface_path)` 构造 `Tmuxd(listen="unix", base_path=f"{surface_path}/tmuxd", ...)`。unix socket 路径有长度上限(103 字节):`<MEMORY_TALK_HOME>/tmuxd/<socket 名>/ttyd.sock` 太长时 tmuxd 起不来并说清楚,把 home 放短一点。
- 开发时 vite 也把 `/surface` 代理过去(`ws: true`)。
- `main.py`:`for path, surface in work_server_svc.surfaces(): app.mount(path, surface)`,放在 `mount_frontend` 之前。
- **门:token 种成只发给 `/surface` 的 cookie。** 现在的门是 `Authorization: Bearer`,而 iframe 加载页面、浏览器开 WebSocket 都带不了自定义头。所以:
  1. 前端进门本来就先问 `GET /api/auth/status`(token 变了会再问)。这次带的 token 有效,响应就顺手 `Set-Cookie: mt_surface=<同一个 token>; Path=/surface; HttpOnly; SameSite=Strict`;无效就清掉。前端一行不用改。
  2. **门不在 tmuxd 里,在最前面**:`gateway.AuthMiddleware`(纯 ASGI,包住整个 app)在 `/surface/*` 下只认这个 cookie,WebSocket 另验 Origin 同源;`tmuxd.asgi()` 不传 `authorize`,自己不设门。tmuxd 文档警告过「不传 authorize 就谁都能进」——这里成立的前提是 mount 在中间件里面,别把 `/surface` 挪到门外。规则表见 [auth.md §1](auth.md)。
  3. 用的就是 Bearer 那个串,所以撤销是白来的:logout(响应也清 cookie)/ 换密码作废 token,cookie 同时失效。cookie 只发往 `/surface`、JS 读不到,不比放在 localStorage 里的 Bearer 多暴露什么。
  4. **不按 worklet 绑。** 原先设想过「拿窗时发一张绑 user + worklet、60 秒一次性的票放进 iframe 地址」,实现时放弃了:前端会刷新 worklet 清单,每次换票 = iframe 地址变 = 终端整页重载;而且 [auth.md §2](auth.md) 本来就不做细粒度权限——进了门的人哪个 work 都能动,窗也一样。窗地址于是稳定为 `/surface/tmuxd/?arg=<id>`。
- `Window.url` / `Window.embed` 变成同源相对地址,前端 iframe 不用再关心 host 和端口。

### 7.7 考虑过、没选的

- **前面放 Caddy / nginx 反代 UDS,`forward_auth` 回 memory.talk 鉴权**:Python 代码最少,但部署从一个进程变两个,和「`memorytalk server daemon` 一条命令起来」相悖。留作生产部署的可选形态——unix socket + base_path 这一半对它同样适用。
- **不要 ttyd,tmuxd 在 ASGI 里自己开 pty 跑 `tmux attach`、自己讲 ttyd 的 WS 协议(或前端直接上 xterm.js)**:少一个子进程、少一跳、不用带 ttyd 二进制;代价是终端协议、resize、流控都自己维护。**接口先定成 `t.asgi()`,这条留作第二阶段**——以后换掉 `asgi()` 的内部,调用方不改。
- **ttyd 仍走 TCP 但只绑 127.0.0.1,转发器连本地端口**:改动最小,但端口冲突、按端口记录的麻烦都还在。只作为过渡。

### 7.8 要留神的

- **同源 iframe**:ttyd 页面和 memory.talk 同源后,它的 JS 能读父页面 localStorage 里的 Bearer token。ttyd 前端是可信代码、xterm 不执行终端输出,风险低;要更紧就把 `/surface` 挂到独立子域做 origin 隔离(`sandbox` 帮不上:ttyd 页面要 `allow-scripts` + `allow-same-origin` 才能连 ws,两者同开等于没沙箱)。
- **长连接**:uvicorn 要装 WebSocket 支持(`uvicorn[standard]`);前面再有代理时空闲超时要放宽。
- **单进程**:ttyd / tmuxd 状态在一个进程里。uvicorn 多 worker 会各起一份 ttyd 争同一个 socket——memory.talk 保持单 worker,这里写明。

---

## 8. 这篇有意不定的事

- ~~server 是进程内的库,还是独立进程~~:先是**库**——tmuxd 在 memory.talk 进程内被 `import`,ttyd 是它的子进程,tmux server 谁的都不是(关掉 memory.talk 现场照跑)。往后按 [work-node.md](work-node.md) 分步搬到每台机器一个的节点进程里:先搬读 agent 记录、往上推这件事,再搬 tmuxd / ttyd,最后才是远程节点。
- ~~协议认领是注册还是约定~~:已定——**server 声明协议(注册)+ default 兜底(约定)**,两者都要,声明优先。
- ~~agent server 是不是终端 server 的一个特例~~:已定——各自独立成文件,**不共用基类**:每个 server 自己写 `__init__`(收注入的 tmuxd)和 `open`(调 `tmuxd.session`),像 controller 一样一眼看全;共用的只有几个小件(解析命令、开 session、把手)。
- ~~纯外链、纯静态页这类没有把手的块要不要也算 server~~:已定——算,`http.py` / `https.py` 就是最薄的 server。
- **把手在 work 层暴露到什么程度**:现在只给销毁(观测改由节点推);`send` 在把手上有,API 不露。给驱动就打开了「memory.talk 编排 agent」这扇门——那是另一个话题,本篇不碰。口子本身(input / output、状态、能力声明)见 [work-server-io.md](work-server-io.md);编排仍不在那篇。
- **远程现场**:块背后的现场在另一台机器上(server 在别处跑)——窗天然是 URL 所以没问题,把手怎么跨机器,和 [work-node.md](work-node.md) 的远程节点一起定。
