# reality 库 — 字段契约(v5)

经验侧:外部世界如实发生过什么。**写门唯一 = [ingest](../../api/v5/ingest.md),客户端按表分**:sessions / rounds 只有 [sync-server](../../works/v5/sync-server.md) 推,conversations 只有各 agent server 推(记录自己的对话);**reality 全局一份、所有 agent 共享只读**。设计推理与 DDL 出处:[works/v5/reality-data.md](../../works/v5/reality-data.md)。引擎通用列与不变性见 [README](README.md)。

## sessions — 会话(写一次就不动)

| 列 | 类型 | 语义 |
|---|---|---|
| `session_id` | TEXT PK | `sess_<…>`,worker 归一时从上游会话派生,全局稳定 |
| `source` | TEXT | 哪个 worker:`claude-code` / `codex` / `openclaw` / … |
| `source_ref` | TEXT | 上游定位(原文件路径 / 上游会话 id),溯源用 |
| `title` | TEXT? | 归一时提取 |
| `started_at` | TEXT? | 上游首轮时间 |

`round_count` / `updated_at` **不落列**(会变的值)→ `v_sessions` 视图从 rounds 现算;`round_count` 同时是 ingest 追加的**乐观游标**。

## rounds — 轮(append-only)

| 列 | 类型 | 语义 |
|---|---|---|
| `session_id`, `idx` | TEXT, INTEGER · PK | `idx` 从 1 起、严格 +1 追加;mind 侧一切 `indexes` 指的就是它 |
| `role` | TEXT | `user` / `assistant` / `tool` / `system`(标准格式统一枚举) |
| `text` | TEXT | 归一后的正文(worker normalize 的产物);**searchable**(语义搜「当时说过什么」) |
| `ts` | TEXT? | 上游时间戳(尽力而为) |
| `meta` | TEXT? | 极少量来源侧结构(JSON 字符串;能摊平的别塞这) |

## conversations — 人 ↔ agent 对话(chat 落盘)

| 列 | 类型 | 语义 |
|---|---|---|
| `conv_id`, `idx` | TEXT, INTEGER · PK | `conv_<ULID>` 对话流(纯传输分组,不承载语义分段)+ 流内序号(1 起 +1) |
| `agent` | TEXT | 哪个 agent 实例的对话(name) |
| `speaker` | TEXT | `human` / `agent` |
| `harness` | TEXT | 说话时该实例的底座:`claude-code` / `codex` / `quickjs`(出处) |
| `text` | TEXT | 消息正文;**searchable**(语义搜「跟管家聊过什么」) |

写入方 = 各 agent server(经 ingest 的 conversations 门,[api/agent](../../api/v5/agent.md));将来可作 mind 的证据源(`type='conversation'`)。

## 视图

| 视图 | 给什么 |
|---|---|
| `v_sessions` | sessions + 现算 `round_count`(= 有效轮数)/ `updated_at`(最后追加时刻) |

## 被 mind 引用的锚点

mind 侧统一以 `(type='session', ref=session_id)` 指过来(proofs / reviews 引证),轮级 = `(session_id, idx)`。软引用、无 FK;reality 不知道也不关心谁引用它。
