# test_card_valid_indexes

`memory-talk card <json>` 场景测试 —— 合法的 `indexes` 表达式应当被接受,
CLI 返回 `{status: ok, card_id: ...}`。

## 场景矩阵

| 测试函数 | `indexes` | 预期 |
|---|---|---|
| `test_card_with_range_indexes` | `"1-3"` | 展开 [1,2,3],成功 |
| `test_card_with_list_indexes` | `"1,3,5"` | 成功 |
| `test_card_with_mixed_range_and_list` | `"1-3,6,9-10"` | 成功 |
| `test_card_with_single_index` | `"2"` | 单个,成功 |
| `test_card_spanning_two_sessions` | 同一 card 引用两个 session 的 rounds | 成功,产生 2 条默认 link |

## 覆盖的路径

- Click argument parsing(`card <body_json>` + `--data-root`)
- JSON body 解析
- `cli/_http.py::api()` 构 httpx client
- FastAPI → `CardService.create()`
- `parse_indexes()` 的正确路径(range / list / 混合 / 单值)
- `CardService.create` 的完整流程:rounds 展开 / 文件落盘 / SQLite 写入 /
  LanceDB embed / 默认 link 生成 / `created` + `card_extracted` 事件发射
- CLI 输出 `{status: "ok", card_id: "card_..."}`

## 为什么 seed 走 service 而不是 CLI sync

Card 测试**只关心** `memory-talk card` 的 CLI 流程。Session 的存在只是 card
创建的前置条件,用 `cli_env.app.state.sessions.ingest(...)` 直接调 service
最省事;走 CLI sync 的话要再搭一份 platform jsonl fixture,分散注意力。

真实的 CLI sync 流程由 `tests/cli/sync/` 专门覆盖。

## 和 invalid scenario 的关系

合法 indexes 全部走通 → `test_card_invalid_indexes/` 补反例。两者**共享一份**
`cli_env` fixture(从 `tests/cli/conftest.py` 继承),数据隔离由 pytest
`tmp_path` 保证。
