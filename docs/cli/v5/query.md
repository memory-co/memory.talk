# query — 唯一的读命令:单发 + 交互(v5 CLI)

自由 SQL 直通两库(调 [`POST /v5/query`](../../api/v5/query.md))。**类 mysql CLI 的双形态**:带 SQL = 单发查询;不带 = 进交互 REPL。

## 单发(one-shot)

```bash
memory.talk query "SELECT card_id, issue FROM v_cards ORDER BY created_at DESC LIMIT 20"
memory.talk query --as-of 2026-06-01 "SELECT * FROM v_card_best WHERE credence > 0"
memory.talk query --json "SELECT count(*) AS n FROM rounds"      # 脚本/AI 消费
memory.talk query --schema                                        # frame 自描述(表/视图/列+注释)
```

| 参数 | 说明 |
|---|---|
| `"<SQL>"` | 仅 `SELECT` / `WITH`(写被 400);表 / 视图 / `semantic()` 见 `--schema` |
| `--as-of <ISO>` | 时光机:整条查询回放到该时刻([seekbase §7](../../works/v5/seekbase.md)) |
| `--json` | `{columns, rows, row_count, truncated}`;默认 markdown 表格 |
| `--schema` | 打印 `GET /v5/schema` —— **AI 先拿这份,再自己写一切查询** |

## 交互模式(REPL,类 mysql)

```
$ memory.talk query
memory.talk (mind + reality attached; as-of: now)
mt> SELECT c.card_id, c.issue, s.score
 -> FROM semantic('cards', '为什么 pty 会想到 tmux') s
 -> JOIN cards c ON c.card_id = s.id LIMIT 5;
┌────────────┬──────────────────────────────┬───────┐
│ card_id    │ issue                        │ score │
├────────────┼──────────────────────────────┼───────┤
│ card_01j…  │ 为什么 pty 会让用户想到 tmux │ 0.87  │
└────────────┴──────────────────────────────┴───────┘
1 row (12 ms)
mt> \as-of 2026-06-01        -- 切时光机(提示符随之标注;\as-of now 回当前)
mt> \d                       -- 列表/视图;\d cards 看列;\sem 看 semantic() 用法
mt> \q
```

- **多行输入,`;` 结束**(mysql 习惯);↑↓ 历史、补全表 / 视图名;
- **反斜杠元命令**:`\d [表]`(schema)、`\as-of <ISO|now>`(会话级时光机)、`\json on|off`、`\q`;
- REPL 只是循环调同一个 `POST /v5/query`——**没有专属能力**,能在 REPL 做的单发都能做。

## 典型查询(两库一条 SQL)

```sql
-- 语义 + 结构化:像这句、且还没答案的卡
SELECT c.card_id, c.issue, s.score
FROM semantic('cards', '…') s JOIN cards c ON c.card_id = s.id
WHERE c.position_count = 0 ORDER BY s.score DESC LIMIT 10;

-- 跨库:这张卡的证据轮原文
SELECT r.idx, r.role, r.text
FROM card_proofs p JOIN rounds r ON r.session_id = p.ref
WHERE p.card_id = 'card_01j…' AND p.type = 'session';
```

> 同一份数据还有**文件查询面**(grep / cat 本地 JSON 镜像,不用起 daemon)——[seekbase §6](../../works/v5/seekbase.md)。SQL 管 join / 聚合 / 语义,grep 管肉眼与脚本。
