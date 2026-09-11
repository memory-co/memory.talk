# API Reference (v5)

本地 API,全部挂在 `/api/` 下,请求 / 响应 JSON。起服务 `memory.talk server start`,`http://127.0.0.1:8000/docs` 有 OpenAPI。

- 机制 / 设计决策见 [`../../designs/v5/`](../../designs/v5/README.md)
- 数据结构 / schema 见 [`../../structure/v5/`](../../structure/v5/README.md)

| 方法 | 端点 | 说明 |
|---|---|---|
| `GET` | `/api/system/health` | 健康检查 |
| `GET` | `/api/system/info` | 运行信息:路径、存储 provider、tmux socket、有没有窗 |
| `GET` | `/api/works` | work 树(森林;root= 只看一棵;created_by= 只看某人建的) |
| `POST` | `/api/works` | 开工:建一个 work(parent= 挂到树上) |
| `GET` | `/api/works/servers` | 有哪些 work server(bash / claude / codex / kimi / http / default)及各自响应的协议;attach 时按协议去找它们 |
| `GET` | `/api/works/{work_id}` | 读一个 work(带身份 = 打开它,记一笔在操作) |
| `PATCH` | `/api/works/{work_id}` | 改目标 / 状态;done 要求子 work 全完;结束后会话冻结 |
| `GET` | `/api/works/{work_id}/canvas` | 画布(视图,随时可重排) |
| `PUT` | `/api/works/{work_id}/canvas` | 全量写画布(version 乐观锁) |
| `GET` | `/api/works/{work_id}/events` | work 自己的时间线 |
| `GET` | `/api/works/{work_id}/inbox` | 收件箱:被 manager.json 路由过来的变动(Collections 的对象、子 work 的状态) |
| `GET` | `/api/works/{work_id}/manager` | 这个 work 的变动打给谁:manager.json,没有则父 work |
| `PUT` | `/api/works/{work_id}/manager` | 改写默认:这棵子树的变动打给指定 work(null = 删掉,回到父) |
| `GET` | `/api/works/{work_id}/recall` | 开工注入:card 目录文本(card → work 的接口) |
| `GET` | `/api/works/{work_id}/sessions` | 会话清单(含活没活着) |
| `POST` | `/api/works/{work_id}/sessions` | 在 work 里打开一个块:协议 → server 建现场,登记会话,交回窗 + 把手 |
| `GET` | `/api/works/{work_id}/users` | user:谁当前正在操作(current)、谁历史操作过(history)。只做可见性,不做权限 |
| `DELETE` | `/api/works/{work_id}/sessions/{session_id}` | 关闭即回收:销毁现场 + 删登记 |
| `POST` | `/api/works/{work_id}/users/touch` | 我在操作这个 work(心跳;身份来自 X-Memory-Talk-User) |
| `POST` | `/api/works/{work_id}/sessions/{session_id}/attach` | 重入:幂等取回同一个现场 |
| `GET` | `/api/works/{work_id}/sessions/{session_id}/capture` | 观测:抓终端屏幕(把手 capture) |
| `GET` | `/api/works/{work_id}/sessions/{session_id}/rounds` | 痕迹:agent 会话的 round(先从把手同步新 round,再读 rounds.jsonl) |
| `GET` | `/api/users` | 所有注册的 user,带活动统计,按最近活动倒序 |
| `POST` | `/api/users` | 注册一个 user(name 唯一;之后请求头 X-Memory-Talk-User 用它) |
| `GET` | `/api/users/me` | 我是谁:X-Memory-Talk-User 对应的 user 档案(没带 → null) |
| `GET` | `/api/users/{name}` | 一个 user 的档案 + 建的 / 动过的 work、最近的提交 |
| `PUT` | `/api/users/{name}` | 改档案(display_name / email) |
| `GET` | `/api/collections/config` | collections.json 本体 + 它的 git 历史(层的变化史) |
| `GET` | `/api/collections/layers` | 有哪些层(最底在前)、各自的 schema 与行为 |
| `POST` | `/api/collections/layers` | 加一个用户层:一份 schema YAML |
| `GET` | `/api/collections/managed` | 某个 work 管的所有对象;不传 work = 没人管的对象 |
| `GET` | `/api/collections/manager` | 这个路径归谁管(最近的 manager.json) |
| `PUT` | `/api/collections/manager` | 在这个目录(或对象)下放 manager.json,绑到一个 work |
| `DELETE` | `/api/collections/manager` | 解绑:删这个目录的 manager.json |
| `GET` | `/api/collections/search` | git grep 整个 Collections(可限定层) |
| `GET` | `/api/collections/tree` | 浏览目录树:对象(带后缀的目录折成一项)、目录、origin 文件 |
| `GET` | `/api/collections/{layer}` | 一层的目录(按目录树列标题) |
| `GET` | `/api/collections/{layer}/recall` | 目录渲染成可注入 agent 的文本 |
| `GET` | `/api/collections/{layer}/{path}` | 读一个对象(rev= 读历史版本) |
| `POST` | `/api/collections/{layer}/{path}` | 建一个对象(一个 [layer] 提交) |
| `PUT` | `/api/collections/{layer}/{path}` | 改一个对象(字段合并;origin 整体替换) |
| `DELETE` | `/api/collections/{layer}/{path}` | 删一个对象(历史在 git) |
| `GET` | `/api/collections/history/{layer}/{path}` | 一个对象的 git log(这一层的分支上) |
| `POST` | `/api/collections/act/{layer}/{action}/{path}` | 行为:schema 之上的领域动作(issue: position / argue / link / spawn / decide;card: discuss) |

分页面:[system.md](system.md) · [works.md](works.md) · [users.md](users.md) · [collections.md](collections.md)

## 通用约定

- **响应信封**:所有 `/api/*` 的响应都是 **`{"data": …, "message": "ok"}`**——分页面里写的响应体是 `data` 那一半。纯文本端点(recall / capture)的 `data` 是那段字符串;删除类端点返回 `200`,`data` 为 `null`(不再有 204)。
- **错误体**:`{"data": null, "error": "<机器码>", "message": "<人读>"}`。

  | 状态 | `error` | 何时 |
  |---|---|---|
  | 400 | `bad_uri` / `no_server` / `cmd_not_found` / `guard` | URI 没协议 / 连 default 都没有 / 命令不在 PATH / 空改动、路径不合法 |
  | 404 | `not_found` / `no_layer` / `no_action` | work、会话、对象、层、行为不存在 |
  | 409 | `exists` / `conflict` / `guard` | 对象已存在 / work 状态、画布、结束后 attach / **跨层提交被守卫拒绝** |
  | 422 | `invalid` | 对象不符合层的 schema(或 FastAPI 默认校验) |
  | 502 | `platform` | tmux 起不来 |

- **身份自报、必须注册、不做权限**:`X-Memory-Talk-User: <名字>` 是谁在操作,名字必须是 `POST /api/users` 注册过的(否则 404)——建 work 时写进 `created_by`,动 work 时记进它的 users,collections 的每个 commit 以它为 **author**(档案里的邮箱,没填则 `<名字>@memory.talk`);不带头 = 匿名,照样能操作。整个实例给一个团队用。
- **Collections 的每个写动作一个 `[层名]` 提交**,写请求可带 `reason`(进 `Reason:`)。跨层的决定是两个相邻提交 + 同一个 `Decision:` / `Discussion:` trailer。
- **时间**:ISO 8601 UTC。**无分页**。**没有鉴权、没有网关**。

## ID

| 对象 | 形态 |
|---|---|
| work | `work_<时间戳><4hex>`;会话 `<work_id>-s<n>` |
| Collections 对象 | **路径**(不含后缀):`memory.talk/配置/该走文件还是环境变量` ↔ 目录 `….issue/`;origin 就是文件路径 |
| position / argument | issue 内顺序编号 `p<n>` / `a<n>` |

## 磁盘

```
~/.memory.talk/collections/   分层 git 仓库(Collections):layer/origin、layer/issue、layer/card(+ 用户层)、stack;工作树跟着 stack
~/.memory.talk/works/    work / user 的记录(MEMORY_TALK_STORE=fs 时):<work_id>/{work,canvas,sessions,users,manager}.json + events/inbox.jsonl + sessions/<sid>/rounds.jsonl
~/.memory.talk/unmanaged.jsonl   没人管的变动
~/.memory.talk/memory.sqlite     MEMORY_TALK_STORE=sqlite 时,上面两样都在这里(works / work_docs / work_logs 三张表)
```

环境变量见 [`../../structure/v5/filesystem.md`](../../structure/v5/filesystem.md)。
