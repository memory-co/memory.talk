# harness — 引擎无关的 harness server API(v5)

harness 起来是一个**常驻 server**([memory-harness](../../works/v5/memory-harness.md));**CC 和 Lua 是两个引擎,但 API 是同一套**——契约钉在 server 层,引擎在后面随便换(CLI `harness chat` / `harness status` 就是这套 API 的薄壳,调用方感知不到底下是谁)。

> 这是 **harness server 自己的 API**(自己的端口),不挂在 memory daemon 的 `/v5` 下——两个进程、两个契约面;harness 对 memory 的访问仍走 [query](query.md) + [写动作](cards.md)(embed-contract 的 ①+④ 通道)。

## POST /harness/chat — 对话(人影响记忆的正门)

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
  "conv": { "conv_id": "conv_01k…", "idx": 8 }   // 本条落在 conversations 的位置(§下)
}
```

- `message` 是**给 harness 的输入**:落不落、怎么落由它决定(可能只回话不动库);`actions` 让「它替你做了什么」透明、可核;
- 单发与交互共用此端点(CLI 交互模式就是循环调它)。

## GET /harness/status

```json
{ "engine": "cc",                        // 或 "lua"(引擎可换,契约不变)
  "state": "governing",                  // idle | ingesting | distilling | governing | consolidating
  "current": "去重扫描 32/74",
  "budget": { "tokens_today_pct": 41 },
  "daemon": "ok", "outbox_pending": 0,
  "engine_version": "v12",               // Lua 引擎:当前生效的自进化版本(cc 引擎为空)
  "recent_actions": [ { "action": "review", "target": "…", "at": "…" } ] }
```

生命周期(start / stop)**不进 API**——那是进程管理,归 CLI / 宿主;server 只答「我是谁、在干嘛」。

## 对话落库:conversations(reality)

**每条 chat 消息(双向)都是经验**,落进 reality 库的 [`conversations` 表](../../structure/v5/reality.md)——经 [ingest 的 conversations 门](ingest.md),harness server 是这个门的唯一客户端:

- 对话可被回放(时光机)、可被语义搜(`semantic('conversations', …)`)、将来可作证据源(`(type='conversation', ref=conv_id)`,mind 的 `(type, ref)` 泛化天然接得住);
- **harness 不因此获得写 reality 的权**:它只能经这个专用门追加**自己的对话记录**,sessions / rounds 仍然只有 sync-server 能写。

## 引擎无关的边界

| | 契约保证 |
|---|---|
| chat / status 的形状 | 两引擎完全一致(本篇) |
| `actions` 的可审计性 | 动作必带引证;引擎不同不改动作集(受治理写动作是唯一的手) |
| 引擎细节 | 只从 `status.engine` / `engine_version` 可见;**不漏进任何请求/响应结构** |
