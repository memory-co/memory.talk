# ingest — reality 库的唯一写门(v5 API)

**客户端按表分**:sessions / rounds 只给 [sync-server](../../works/v5/sync-server.md)(worker normalize 后推入);`conversations` 只给各 agent server(记录自己的对话,[agent API](agent.md))。宿主谁都不该碰。这套契约就是 sync 剥离的边界面——语义从 v4 的 `ensure_session` / `append_rounds` 平移,按 v5 两库分治收编到 `/v5/ingest`。

## POST /v5/ingest/sessions — ensure(建或对游标)

```json
{ "session_id": "sess_40abf0e0…",       // worker 归一时从上游派生(全局稳定)
  "source": "claude-code",
  "source_ref": "~/.claude/projects/…/xxx.jsonl",
  "title": "配 pty 那次",                 // 可选
  "started_at": "2026-07-01T09:00:00Z" }  // 可选
```

幂等:不存在 → 建 session 行(写一次就不动);已存在 → 不动。两种情况都返回**当前游标**:

```json
{ "session_id": "sess_40abf0e0…", "cursor": 41 }   // = v_sessions.round_count
```

## POST /v5/ingest/sessions/{session_id}/rounds — 追加轮(乐观并发)

```json
{ "expected_cursor": 41,                // 我以为的当前轮数
  "rounds": [                            // 标准格式(worker normalize 的产物)
    { "role": "user",      "text": "…", "ts": "…", "meta": null },
    { "role": "assistant", "text": "…", "ts": "…", "meta": null }
  ] }
```

- `idx` **服务端 mint**(从 cursor+1 严格 +1)——worker 不给轮号;
- `expected_cursor ≠ 当前` → **409** + 服务端游标(worker 按它重拉重推,幂等收敛——[sync-server §3](../../works/v5/sync-server.md) 的 push 契约);
- 成功 → `{"session_id": …, "cursor": 43, "appended": 2}`。

## POST /v5/ingest/conversations — 追加对话消息(agent server 专用)

```json
{ "conv_id": "conv_01k…",              // 对话流 id(agent server 起流时 mint)
  "agent": "curator",                    // 哪个实例
  "harness": "claude-code",              // 该实例当下的底座(出处)
  "messages": [
    { "speaker": "human", "text": "card_01j… 那张卡过时了…" },
    { "speaker": "agent", "text": "收到。我读了 sess_9f2…,加了 #p3…" }
  ] }
```

- `idx` 服务端 mint(流内 1 起严格 +1),追加语义同 rounds;
- 成功 → `{"conv_id": …, "cursor": 8, "appended": 2}`;
- **这不是 agent 写 reality 的口子**:它只能追加**自己的对话记录**;sessions / rounds 对它依旧无门。

## 边界

- **只进不出**:ingest 没有读端点(读走 [query](query.md));没有改、没有删(reality append-only,引擎焊死);
- **权属**:本地形态靠 loopback;云端形态 ingest 走独立 token(与查询 token 分权),且 sessions 门与 conversations 门**各自发 token**(sync-server / agent server 互不越权);
- 上游洪峰的限流 / 断线缓冲在 sync-server 侧(它攒批重试),ingest 只管单次请求的原子追加。
