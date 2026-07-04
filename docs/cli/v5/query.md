# query — 唯一的读命令(v5 CLI)

自由 SQL 直通两库(调 [`POST /v5/query`](../../api/v5/query.md))。**会写 SQL 就会用整个 v5 的读面**——没有别的读命令要学。

```bash
memory.talk query "<SQL>" [--as-of <ISO>] [--json]
memory.talk query --schema                      # frame 自描述(表/视图/列+注释)
```

## 用法

```bash
# 结构化:最近建的卡
memory.talk query "SELECT card_id, issue, created_at FROM v_cards ORDER BY created_at DESC LIMIT 20"

# 语义 + 结构化,一条链:像这句、且还没有答案的卡
memory.talk query "SELECT c.card_id, c.issue, s.score
                   FROM semantic('cards', '为什么 pty 会想到 tmux') s
                   JOIN cards c ON c.card_id = s.id
                   WHERE c.position_count = 0 ORDER BY s.score DESC LIMIT 10"

# 跨库 join:这张卡的证据轮原文
memory.talk query "SELECT r.idx, r.role, r.text
                   FROM card_proofs p JOIN rounds r ON r.session_id = p.ref
                   WHERE p.card_id = 'card_01j…' AND p.type = 'session'"

# 时光机:上个月它信什么
memory.talk query --as-of 2026-06-01 "SELECT * FROM v_card_best WHERE credence > 0"
```

| 参数 | 说明 |
|---|---|
| `"<SQL>"` | 仅 `SELECT` / `WITH`(写被 400);表 / 视图 / `semantic()` 见 `--schema` 或 [structure/v5](../../structure/v5/README.md) |
| `--as-of <ISO>` | 整条查询回放到该时刻([seekbase 时光机](../../works/v5/seekbase.md)) |
| `--schema` | 打印 frame 自描述(`GET /v5/schema`)——**AI 先拿这份,再自己写一切查询** |
| `--json` | `{columns, rows, row_count, truncated}` 结构化输出;默认 markdown 表格 |

超行数上限时输出尾部标 `(truncated)`——收窄 SELECT 或加 LIMIT。

> 顺手一提:同一份数据还有**文件查询面**(grep / cat 本地 JSON 镜像,不用起 daemon)——[seekbase §6](../../works/v5/seekbase.md)。SQL 管 join / 聚合 / 语义,grep 管肉眼与脚本,随时并用。
