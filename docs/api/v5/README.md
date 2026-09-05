# API (v5)

> **状态:issue 与 card 两层已实现(最简版),task / server 两层未实现。** 起服务:`cd backend && python -m backend serve`,然后看 `http://127.0.0.1:8000/docs`(OpenAPI)。本页只列端点,机制见 [docs/works/v5](../../works/v5/README.md)。

通用约定:请求 / 响应 JSON;错误体 `{"error": "<机器码>", "message": "<人读>"}`,`404 not_found` / `409 exists` / `500 git`;每个写动作是 memory 仓库里的**一个 commit**,写请求可带 `reason`(进 commit message)和 `origin`(`{task_id, rounds}`,出处)。**没有鉴权**(网关随 task 层一起做)。

| 方法 | 端点 | 说明 |
|---|---|---|
| `GET` | `/api/system/health` | 健康检查 |
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
