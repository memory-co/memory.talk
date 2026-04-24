# test_log_valid

`memory-talk log <id>` 读取 card 或 session 的生命周期事件流。

## 场景

种子:一条 session(`imported`) → 基于它创建 card(`created` + session.`card_extracted`)
→ 用户 link card↔session(两端各一条 `linked`) → 给 session 加 tag(`tag_added`)。

| 测试函数 | 验证什么 |
|---|---|
| `test_log_session_streams_all_lifecycle_events` | `log <session_id>` 返回的 kinds 含 `imported` / `card_extracted` / `linked` / `tag_added`(顺序不锁死,这里只检 superset) |
| `test_log_card_streams_created_and_linked` | `log <card_id>` 返回 **exactly** `["created", "linked"]`(card 自己的事件流,不包含 session 独有的事件) |
| `test_log_events_sorted_ascending_by_at` | 事件按 `at` 升序排 |
| `test_log_event_detail_shape` | `created.detail` 含 summary / rounds / default_links / ttl_initial;`linked.detail` 含 direction / peer_id / peer_type / comment |

## 覆盖的代码路径

- Click `log <object_id>` 命令
- `cli/log.py` 构 `{"id": object_id}` body
- `api/log.py`:前缀分发(card_* vs sess_*)
- `CardService.log()` / `SessionService.log()`:读对象各自的 `events.jsonl`
- `F.read_card_events()` / `F.read_session_events()`:文件层读取
- 按 `at` 字段升序排序 +  `{at, kind, detail}` 三字段输出

## 事件是从哪里来的

v2 的事件**随写自动发射**,`log` 命令只读。所以种子阶段的每一步都在
累积事件,`log` 命令就是把这些事件按时间线回放。

具体触发点:
- `SessionService.ingest()` → `imported`
- `CardService.create()` → `created`(card 侧) + `card_extracted`(session 侧)
- `LinkService.create()` → `linked` × 2(两端各一条,direction 不同)
- `SessionService.add_tags()` → 每个真新增的 tag 一条 `tag_added`

种子走 service 直调,不走 CLI —— log 命令才是被测对象。

## 和 invalid 场景的关系

`test_log_invalid/` 覆盖错误路径(bad 前缀、不存在的 id)。
