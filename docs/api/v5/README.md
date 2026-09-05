# API (v5)

> **状态:task / server / issue / card 四层都有最简实现。** 起服务:`cd backend && python -m backend serve`,然后看 `http://127.0.0.1:8000/docs`(OpenAPI)。本页只列端点,机制见 [docs/works/v5](../../works/v5/README.md)。

通用约定:请求 / 响应 JSON;错误体 `{"error": "<机器码>", "message": "<人读>"}`,`404 not_found` / `409 exists` / `500 git`;每个写动作是 memory 仓库里的**一个 commit**,写请求可带 `reason`(进 commit message)和 `origin`(`{task_id, rounds}`,出处)。**没有鉴权、没有网关**(ttyd / 反代 / 静态托管随前端一起做)。

| 方法 | 端点 | 说明 |
|---|---|---|
| `GET` | `/api/system/health` | 健康检查 |
| `GET` | `/api/system/info` | 运行信息:路径、tmux socket、有没有窗 |
| `GET` | `/api/tasks` | task 树(森林;root= 只看一棵) |
| `POST` | `/api/tasks` | 开工:建一个 task(parent= 挂到树上) |
| `GET` | `/api/tasks/{task_id}` | 读一个 task |
| `PATCH` | `/api/tasks/{task_id}` | 改目标 / 项目 / 状态;done 要求子 task 全完;结束后成员冻结 |
| `GET` | `/api/tasks/{task_id}/canvas` | 画布(视图,随时可重排) |
| `PUT` | `/api/tasks/{task_id}/canvas` | 全量写画布(version 乐观锁) |
| `GET` | `/api/tasks/{task_id}/events` | task 自己的时间线 |
| `GET` | `/api/tasks/{task_id}/members` | 成员清单(含活没活着) |
| `POST` | `/api/tasks/{task_id}/members` | 在 task 里打开一个块:协议 → server 建现场,登记成员,交回窗 + 把手 |
| `GET` | `/api/tasks/{task_id}/recall` | 开工注入:card 目录文本(card → task 的接口) |
| `DELETE` | `/api/tasks/{task_id}/members/{member_id}` | 关闭即回收:销毁现场 + 删登记 |
| `POST` | `/api/tasks/{task_id}/members/{member_id}/attach` | 重入:幂等取回同一个现场 |
| `GET` | `/api/tasks/{task_id}/members/{member_id}/capture` | 观测:抓终端屏幕(把手 capture) |
| `GET` | `/api/tasks/{task_id}/members/{member_id}/rounds` | 痕迹:agent 会话的 round(先从把手同步新 round,再读 rounds.jsonl) |
| `GET` | `/api/servers` | server 清单及各自认领的协议 |
| `GET` | `/api/servers/resolve` | 这个 URI 会请求到哪个 server(不建现场) |
| `GET` | `/api/cards` | 目录(按目录分层的标题清单;召回注入的就是它) |
| `POST` | `/api/cards` | 写一张卡(一个 commit) |
| `GET` | `/api/cards/recall` | 目录渲染成可直接注入 agent 上下文的文本 |
| `GET` | `/api/cards/search` | git grep 词条正文 |
| `GET` | `/api/cards/{card_id}` | 读一张卡(可指定历史版本) |
| `PUT` | `/api/cards/{card_id}` | 改一张卡(一个 commit,旧内容进历史) |
| `DELETE` | `/api/cards/{card_id}` | 废弃一张卡(文件留着,标 deprecated) |
| `GET` | `/api/cards/{card_id}/history` | 这张卡的 git log |
| `POST` | `/api/cards/{card_id}/issue` | 对这张卡不同意:开一个 issue 挂上去当讨论页(一个 commit) |
| `GET` | `/api/issues` | issue 清单(标注时「指认既有问题」查的就是它) |
| `POST` | `/api/issues` | 提一个问题(一个 commit) |
| `GET` | `/api/issues/search` | git grep 问题 / 立场 / 论证 |
| `GET` | `/api/issues/{issue_id}` | 读一个 issue:立场按现算 credence 排序 |
| `POST` | `/api/issues/{issue_id}/card` | 争出结果:把某个立场写成一张卡(issue + card 同一个 commit) |
| `GET` | `/api/issues/{issue_id}/history` | 这个 issue 的 git log(辩论序列) |
| `POST` | `/api/issues/{issue_id}/links` | issue 之间连一条 IBIS 边 |
| `PUT` | `/api/issues/{issue_id}/manager` | 绑 / 换 / 解绑 manager task |
| `POST` | `/api/issues/{issue_id}/positions` | 加一个立场(只增不改) |
| `POST` | `/api/issues/{issue_id}/positions/{position_id}/arguments` | 对某个立场表态:+1 / 0 / -1,带证据 |
| `POST` | `/api/issues/{issue_id}/positions/{position_id}/tasks` | 为验证这个立场派出一个 task(先只记 id) |
## task / server 那半

- **task 是裸文件**:`~/.memory.talk/tasks/<task_id>/{task.json, canvas.json, members.json, events.jsonl, sessions/<member>/rounds.jsonl}`,不进 git。
- **成员 = 现场**:`POST /api/tasks/{id}/members {uri}` 看协议找 server 建现场,登记成员(id 形如 `<task_id>-m1`,脱离布局),交回 `window`(画布 iframe 装的地址)和 `handle`(把手能干什么)。没配 `MEMORY_TALK_TTYD_URL` 时终端类成员 `window.url` 老实报 `null`。
- **server 认领**:`agent` 显式认领 `claude` / `codex`;`browser` 认领 `http` / `https`;`files` 认领 `file`;`terminal` 按约定兜底认领 PATH 里任何命令名。找不到 → `400 no_server`。
- **把手**:终端 / agent 成员有 `capture`(抓屏);agent 成员多一项 `rounds`(从 Claude Code / Codex 的记录文件读 round,append-only 追加进 `rounds.jsonl`)。`send` 只在进程内,不暴露 API。
- **结束**:`PATCH {status: done}` 要求子 task 全完;结束后现场销毁、登记留着、不再能 attach。
- 环境变量:`MEMORY_TALK_HOME` / `MEMORY_TALK_WORKSPACE` / `MEMORY_TALK_TMUX_SOCKET` / `MEMORY_TALK_TTYD_URL` / `MEMORY_TALK_CLAUDE_PROJECTS` / `MEMORY_TALK_CODEX_SESSIONS`。

## 路径规则

- `card_id` 是仓库内相对路径(不含 `.md`),目录即分类:`memory.talk/配置只来自环境变量` ↔ `cards/memory.talk/配置只来自环境变量.md`。建卡时给 `dir` + `title`(或显式 `slug`)。
- `issue_id` 形如 `iss_<时间戳><4hex>`;立场 id `p1, p2…`,论证 id `a1, a2…`,都在 issue 内顺序编号、只增不改。
- `GET /api/cards/{id}?rev=<sha>` 读历史版本;sha 来自 `/history`。

## 两个跨对象的动作(同一个 commit)

- `POST /api/issues/{id}/card`:争出结果,issue 记 `card` + 新建卡(卡的 `issue` 指回来)。
- `POST /api/cards/{id}/issue`:对一张卡不同意,新建 issue 挂到卡上(卡的 `issue` 指过去,issue 的 `card` 指回来)。

## 磁盘上长什么样

```
~/.memory.talk/memory/            ← git 仓库
├── cards/<dir>/<slug>.md         ← frontmatter(title / context / links / issue / status)+ 正文
└── issues/<issue_id>.json        ← question / origin / manager_task / card / positions[] / links[]
```

```
d3a5641 card: deprecate memory.talk/配置只来自环境变量
487d55f decide: iss_…#p2 -> card memory.talk/配置只来自环境变量      ← issue + card 同一 commit
50f1fdf issue: argue iss_…#p2 +1                                    ← body: Task: task_try / Rounds: 9
5c0282a issue: spawn iss_…#p2 -> task_try
ee0875e issue: position iss_…#p2: 只用环境变量,不要配置文件
dd84ba9 issue: manage iss_… by task_root
61137ff issue: raise iss_…: memory.talk v5 的配置该走文件还是环境变量?
```
