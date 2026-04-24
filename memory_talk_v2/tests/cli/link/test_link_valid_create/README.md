# test_link_valid_create

`memory-talk link create <json>` 合法用户 link 创建场景。覆盖所有允许的
(source_type, target_type) 组合,并验证两端事件都被发射。

## 场景

| 测试函数 | (source_type → target_type) | 特殊点 |
|---|---|---|
| `test_link_card_to_session` | card → session | 返回 `link_id` + `ttl == settings.ttl.link.initial` |
| `test_link_card_to_card_with_comment` | card → card | `comment` 被持久化 |
| `test_link_session_to_session` | session → session | 支持同类型互链 |
| `test_link_create_emits_events_on_both_ends` | card → session | 两端各一条 `linked` 事件,`direction` 分别 outgoing / incoming,`peer_id` 互指 |

## 覆盖的代码路径

- Click `link create <json>` 子命令
- `cli/link.py` JSON body 解析 + POST
- `LinkService.create()` 的 prefix 校验、存在性校验、comment 长度校验
- SQLite `links.insert()` + 文件层 `write_link()`
- **双端事件**:`events.emit(source_id, "linked", direction=outgoing, ...)` +
  `events.emit(target_id, "linked", direction=incoming, ...)`,各落到自己的
  `events.jsonl`
- 响应 `{status, link_id, ttl}`

## 和 invalid 场景的关系

- 共享 `cli_env` fixture(`tests/cli/conftest.py`)
- 种子数据模式相同(两个 session + 两个 card)
- `invalid_create/` 用反例验证所有拒绝路径 + 事务性(失败不落 link)
