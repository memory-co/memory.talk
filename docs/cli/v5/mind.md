# mind — 问信念库(v5 CLI)

进 **mind 库**(cards / positions / reviews / links / proofs + 视图,[字段契约](../../structure/v5/mind.md))的查询命令。类 mysql 双形态:带 SQL 单发,不带进 REPL。调 [`POST /v5/query`](../../api/v5/query.md)(`library: "mind"`)。

> **可见性:只有 mind**——两库完全分开,互不 ATTACH。mind 里指向证据的只有**指针**(`(type, ref, indexes)`,proofs / reviews 引证);要看证据原文,按 type 去对应的面解析(session 型 → [reality](reality.md);file 型 → 文件)——**两步取证**,mind 不偏爱任何一种证据存储(这正是 `(type, ref)` 泛化的意义:file 型证据根本不在库里,join 本来就不可能对所有型成立)。

## 单发

```bash
memory.talk mind "SELECT card_id, issue FROM v_cards ORDER BY created_at DESC LIMIT 20"

# 语义 + 结构化:像这句、且还没答案的卡
memory.talk mind "SELECT c.card_id, c.issue, s.score
                  FROM semantic('cards', '为什么 pty 会想到 tmux') s
                  JOIN cards c ON c.card_id = s.id
                  WHERE c.position_count = 0 ORDER BY s.score DESC LIMIT 10"

# 两步取证:① mind 查证据指针
memory.talk mind "SELECT type, ref, indexes FROM card_proofs WHERE card_id = 'card_01j…'"
#   → session | sess_9f2… | 36-41
# ② 按 type 解析:session 型 → reality 查原文
memory.talk reality "SELECT idx, role, text FROM rounds
                     WHERE session_id = 'sess_9f2…' AND idx BETWEEN 36 AND 41"

memory.talk mind --as-of 2026-06-01 "SELECT * FROM v_card_best WHERE credence > 0"   # 时光机
memory.talk mind --schema                                                            # mind 侧自描述
```

| 参数 | 说明 |
|---|---|
| `"<SQL>"` | 仅 `SELECT` / `WITH`;表 / 视图 / `semantic()` 见 `--schema` |
| `--as-of <ISO>` | 时光机([seekbase §7](../../works/v5/seekbase.md)) |
| `--schema` | mind 的表 / 视图 / 列 + 注释 |
| `--json` | `{columns, rows, row_count, truncated}`;默认 markdown 表格 |

## 交互模式(REPL,类 mysql)

```
$ memory.talk mind
memory.talk · mind (read-only; as-of: now)
mind> SELECT count(*) FROM v_cards;
…
mind> \as-of 2026-06-01      -- 会话级时光机(\as-of now 回当前)
mind> \d v_positions         -- \d 列表;\d <表> 看列;\sem 看 semantic() 用法
mind> \json on
mind> \q
```

多行输入 `;` 结束、↑↓ 历史、表名补全;元命令 `\d` / `\as-of` / `\json` / `\q`。REPL 没有专属能力——循环调同一个端点。

> 写不在这:mind 库只接受 harness 的受治理写动作;人要改,[`harness chat`](harness.md) 说给管家。
