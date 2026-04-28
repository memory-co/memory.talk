# test_compile_for_tables

`compile_for(preds, table)` 把谓词列表落成 SQL 片段,并强制每个字段只能用在
对应的表上。

## 场景矩阵

| 测试函数 | 输入 | 预期 |
|---|---|---|
| `test_compile_for_sessions_with_source` | `source = "claude-code" AND tag = "decision"` → `sessions` | SQL 含 `sessions.source = ?` 和 `json_each(sessions.tags)`,params 顺序与谓词一致 |
| `test_compile_for_cards_rejects_sessions_only_field` | `source = "claude-code"` → `cards` | 返回 `None`(整个谓词集都是 sessions-only,不可应用到 cards)|
| `test_compile_for_sessions_rejects_cards_only_field` | `card_id = "card_x"` → `sessions` | 返回 `None`(card_id 是 cards-only)|

## 覆盖的代码路径

- `util/dsl.py::compile_for(preds, table)` 主流程
- 字段-表 白名单(`source` 只能 sessions、`card_id` 只能 cards)
- `tag = "x"` 在 sessions 表上展开成 `EXISTS (SELECT 1 FROM json_each(sessions.tags) WHERE value = ?)`
- params 与 SQL `?` 占位符一一对应

## 为什么不可应用就返回 None 而不是抛错

`compile_for` 是双表分发(cards 和 sessions 走不同的 compile),搜索层的策略是:
- 谓词只命中 sessions → cards 桶 `compile_for(..., "cards") == None`,整个 cards 桶**跳过**;
- 谓词只命中 cards → sessions 桶**跳过**;
- 两边都能 compile → 双桶都查、合并。

抛错会让"用户写了 cards-only 字段 + 想搜 sessions"变成 500;返回 None 让搜索
自然降级为"sessions 桶空集"。
