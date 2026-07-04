# API (v5)

v5 的 HTTP 契约,prefix `/v5`。**跟 v4 的根本区别:读不再每问法一端点**——查询统一走 [`POST /v5/query`](query.md)(自由 SQL,[表结构即 API](../../structure/v5/README.md)),端点只剩**三类**:

| 类 | 端点 | 谁用 | 文档 |
|---|---|---|---|
| **查**(唯一读面) | `POST /v5/query`(`library: mind\|reality`)· `GET /v5/schema` | 所有人(harness / 宿主 / 人) | [query.md](query.md) |
| **写 mind**(受治理动作) | `POST /v5/cards…` · `POST /v5/reviews` · `DELETE /v5/cards/{id}` | 只有 harness | [cards.md](cards.md) |
| **写 reality**(摄入) | `POST /v5/ingest/…` | sync-server(sessions/rounds)+ harness server(conversations) | [ingest.md](ingest.md) |
| **harness server**(独立进程,自己的端口) | `POST /harness/chat` · `GET /harness/status` | 人 / 宿主(CLI 薄壳) | [harness.md](harness.md) |

另有 `GET /v5/status`(daemon 健康 / 两库计数 / outbox 深度,形态从 v4 status 平移,不单开文档)。

## 设计规则

- **读写不对称是特性**:读彻底自由(SQL),写只有窄门(动作)——[query-interface §2](../../works/v5/query-interface.md) 的「问自由,改受治理」;
- **两库写门互斥**:mind 动作写不了 reality,ingest 写不了 mind——库级权属([README](../../structure/v5/README.md))在路由层就分开;
- **v4 的 read / search / recall / list 端点不再有 v5 对应**——都是 [query](query.md) 上的一条 SQL;CLI 也只有四命令(mind / reality / sync / harness,见 [cli/v5](../../cli/v5/README.md)),人写 mind 走 `harness chat`(说给管家),不直接调写动作;
- 本地形态免认证(loopback);云端形态(seekbase §9)所有端点过 token——契约不变,传输加壳。

机制推理见 [works/v5](../../works/v5/README.md);错误响应统一 `{"detail": "<msg>"}` + 4xx/5xx(沿 v4)。
