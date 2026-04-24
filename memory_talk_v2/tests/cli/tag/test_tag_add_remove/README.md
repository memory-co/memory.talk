# test_tag_add_remove

`memory-talk tag {add,remove} <sess_id> <tags...>` 的完整生命周期 + 幂等性测试。

## 关键不变式

v2 的 tag 操作是**按真实变化发事件**:

- `add` 一个已有的 tag → 不改 state、**不发事件**
- `remove` 一个不存在的 tag → 不改 state、**不发事件**
- 一次 `add decision important`,若 `decision` 已存在、`important` 是新的 →
  **只发一条 `tag_added` 事件**(给 important)

## 场景矩阵

| 测试函数 | 验证什么 |
|---|---|
| `test_add_single_tag` | `tag add sid decision` → 返回 `tags=["decision"]` |
| `test_add_multiple_tags_in_one_call` | `tag add sid a b c` → 三条 `tag_added` 事件 |
| `test_add_existing_tag_is_idempotent` | 再 `add decision` → 只有 1 条事件(第一次那条) |
| `test_add_mixed_new_and_existing` | `add decision important` 时 decision 已存在 → 只发 important 那一条 |
| `test_remove_tag` | `remove decision` → 返回剩下的 tags + 一条 `tag_removed` |
| `test_remove_nonexistent_tag_is_idempotent` | `remove never-was-here` → state 不变、**零事件** |
| `test_full_lifecycle` | 组合场景 → 只有真实状态变化发事件,总共 3 added + 3 removed |

## 覆盖的代码路径

- Click `tag` group + `add` / `remove` subcommands,`nargs=-1 required=True`
- `cli/tag.py::_call()` 构 `{session_id, tags}` body
- `SessionService.add_tags()` / `remove_tags()`:
  - Pydantic `TagsRequest` 校验
  - 计算 diff(`newly_added` / `truly_removed`)
  - 持久化 `session.tags`(SQLite + meta.json 双写)
  - 每个真实变动调 `events.emit(session_id, "tag_added"|"tag_removed", ...)`
- 响应 `{status, tags}`(tags 是**全量**而不是 diff)

## 事件副作用断言

每个 case 都读 `session.events.jsonl` 过滤 `tag_*` 事件,精确断言次数:
- 有变化 → 有事件
- 无变化 → 无事件

这条断言守护"**幂等 no-op 不污染事件流**"这个语义 —— 否则几千次空 add 会
把 session log 填满。
