# reality — 问经验库(v5 CLI)

进 **reality 库**(sessions / rounds + `v_sessions`,[字段契约](../../structure/v5/reality.md))的查询命令。形态与 [mind](mind.md) 完全同构(单发 / REPL / `--as-of` / `--schema` / `--json`、`;` 结束、`\d` 元命令),不重复;调 [`POST /v5/query`](../../api/v5/query.md)(`library: "reality"`)。

> **可见性:只有 reality**——两库完全分开,互不 ATTACH。想知道「这段经验产出了什么信念」,去 [mind](mind.md) 查指针:`SELECT card_id FROM card_proofs WHERE type='session' AND ref='sess_…'`(两步取证的反向)。

## 用法

```bash
# 最近进来的 session
memory.talk reality "SELECT session_id, source, title, round_count, updated_at
                     FROM v_sessions ORDER BY updated_at DESC LIMIT 20"

# 语义搜「当时说过什么」(rounds.text 是 searchable)
memory.talk reality "SELECT r.session_id, r.idx, r.text, s.score
                     FROM semantic('rounds', '配 pty 提到 tmux') s
                     JOIN rounds r ON r.session_id || ':' || r.idx = s.id
                     ORDER BY s.score DESC LIMIT 10"

# 某个 session 的完整对话
memory.talk reality "SELECT idx, role, text FROM rounds
                     WHERE session_id = 'sess_9f2…' ORDER BY idx"

$ memory.talk reality          # REPL
memory.talk · reality (read-only; as-of: now)
reality>
```

## 边界

- **只读**(库本身对人 / harness 都只读——唯一写入方是 [sync-server 的 ingest](../../api/v5/ingest.md));
- 经验有没有进来、卡在哪 → [`sync status`](sync.md);
- 想知道「这段经验产出了什么信念」→ [mind](mind.md) 按 `(type='session', ref)` 查 proofs(两步取证)。
