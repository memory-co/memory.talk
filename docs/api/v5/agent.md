# agent — 实例控制面 + harness 无关的 server API(v5)

agent 是**实例化**的记忆管家([works/v5/agent.md](../../works/v5/agent.md)):每个实例 = `name` + `harness`(`claude-code` / `codex` / `lua`)+ 独立 mind 库 + 常驻 server。**API 钉在 server 层,三种 harness 同一套契约**——底座细节只出现在 `status.harness`,不漏进任何请求 / 响应结构。

## 实例管理(registry)

```
POST /v5/agents                       { "name": "curator", "harness": "claude-code" }
                                      → 建实例:注册 + 建它的 mind 库(空图)
GET  /v5/agents                       → [{ name, harness, state, created_at }]
GET  /v5/agents/{name}/status         → 见下
DELETE /v5/agents/{name}              → 注销实例(mind 库墓碑;经验与对话记录留在 reality)
```

生命周期(start / stop 进程)归 CLI / supervisor,不进 registry API。

## POST /v5/agents/{name}/chat — 对话(人影响该实例记忆的正门)

```json
{ "message": "card_01j… 那张卡的最优答案过时了,新结论在昨天那个 session 里" }
```

响应:

```json
{
  "reply": "收到。我读了 sess_9f2…:38-52,给 card_01j… 加了 #p3 并踩了 #p1(-1)。",
  "actions": [                          // 本轮实际执行的受治理写动作(带引证,可审计)
    { "action": "add_position", "target": "card_01j…#p3",
      "proof": { "type": "session", "ref": "sess_9f2…", "indexes": "38-52" } },
    { "action": "review", "target": "card_01j…#p1", "argument": -1 }
  ],
  "conv": { "conv_id": "conv_01k…", "idx": 8 }
}
```

`message` 是给该 agent 的输入:落不落、怎么落由它决定(动作只写**它自己的 mind 库**);每条消息(双向)落 reality 的 `conversations`(带 `agent` 字段,经 [ingest 的 conversations 门](ingest.md))。

## GET /v5/agents/{name}/status

```json
{ "name": "curator", "harness": "claude-code",
  "state": "governing",                 // idle | ingesting | distilling | governing | consolidating
  "current": "去重扫描 32/74",
  "budget": { "tokens_today_pct": 41 },
  "daemon": "ok", "outbox_pending": 0,
  "engine_version": "v12",              // lua harness:当前生效的自进化版本;其余为空
  "recent_actions": [ { "action": "review", "target": "…", "at": "…" } ] }
```

## POST /v5/agents/{name}/query — 查该实例的 mind 库

```json
{ "sql": "SELECT * FROM v_card_best WHERE credence > 0 LIMIT 20",
  "as_of": "2026-06-01T00:00:00Z" }      // 可选,时光机
```

语义同 [query](query.md)(SELECT/WITH 白名单、semantic()、行数上限),只是**库 = 该 agent 的 mind**;`GET /v5/agents/{name}/schema` 同理。共享 reality 的查询走全局 [`POST /v5/query`](query.md)。

## 写动作在哪

受治理写动作([cards.md](cards.md))全部挂在实例下:`POST /v5/agents/{name}/cards…` ——**只有该 agent 自己调**(动作写它自己的 mind 库);没有全局的写端点。

## harness 无关的边界

| | 契约保证 |
|---|---|
| chat / status / query 的形状 | 三种 harness 完全一致(本篇) |
| `actions` 可审计 | 动作必带引证;harness 不同不改动作集 |
| 底座细节 | 只从 `status.harness` / `engine_version` 可见 |
