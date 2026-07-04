# API (v5)

v5 的 HTTP 契约,prefix `/v5`。**跟 v4 的根本区别:读不再每问法一端点**——查询统一走自由 SQL([表结构即 API](../../structure/v5/README.md)):reality 走 [`POST /v5/query`](query.md),各 agent 的 mind 走 [`/v5/agents/{name}/query`](agent.md)。端点只剩**四类**:

| 类 | 端点 | 谁用 | 文档 |
|---|---|---|---|
| **查 reality**(共享经验) | `POST /v5/query` · `GET /v5/schema` | 所有人(agent / 宿主 / 人) | [query.md](query.md) |
| **agent 实例**(registry / chat / status / 各自 mind 的查询) | `/v5/agents…` · `/v5/agents/{name}/chat·status·query` | 人 / 宿主(CLI 薄壳) | [agent.md](agent.md) |
| **写 mind**(受治理动作,按实例) | `POST /v5/agents/{name}/cards…` 等 | 只有该 agent 自己 | [cards.md](cards.md) |
| **写 reality**(摄入) | `POST /v5/ingest/…` | sync-server(sessions/rounds)+ agent server(conversations) | [ingest.md](ingest.md) |

另有 `GET /v5/status`(daemon 健康 / 各库计数 / outbox 深度,形态从 v4 status 平移,不单开文档)。

## 设计规则

- **读写不对称是特性**:读彻底自由(SQL),写只有窄门(动作)——[query-interface §2](../../works/v5/query-interface.md) 的「问自由,改受治理」;
- **写门互斥且按实例**:mind 动作只写该 agent 自己的库、写不了 reality;ingest 写不了任何 mind——库级权属([README](../../structure/v5/README.md))在路由层就分开;
- **v4 的 read / search / recall / list 端点不再有 v5 对应**——都是一条 SQL([query](query.md) / agent 的 mind query);CLI 三顶层命令(reality / sync / agent,见 [cli/v5](../../cli/v5/README.md)),人写 mind 走 `agent chat`(说给管家),不直接调写动作;
- 本地形态免认证(loopback);云端形态(seekbase §9)所有端点过 token——契约不变,传输加壳。

机制推理见 [works/v5](../../works/v5/README.md);错误响应统一 `{"detail": "<msg>"}` + 4xx/5xx(沿 v4)。
