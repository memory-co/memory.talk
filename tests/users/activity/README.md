# users / activity — 建了几个、动过几个、正在看哪些

## 这个场景在测什么
`GET /api/users` / `GET /api/users/{name}` 上的派生统计(现算,不落盘;`docs/designs/v5/user.md §3`):
- `works_created` / `works_created_ids`:works.db 的 `created_by`;
- `works_touched` / `works_touched_ids`:worktrace.db 里这个人留过痕的 work——开过段(`user_id`)、结束过段(`end_user_id`)、打过点(`user_id`);
  读、心跳不算;id 按 work id 升序;
- `active_works`:`works.viewers` 里有他的 work(心跳 120 秒一窗,离开立刻拿掉);
- `last_seen`:建 work 的时刻、轨迹里最后一次出现、metas 提交里最晚的那个,统一成 UTC 到秒(`…Z`);清单和档案算出来的一致。

## 不在这测什么
- 谁在看(心跳、离开、超时、重启清空)本身 → `works/viewers`
- 归属(created_by)→ `work_ownership`;提交数 → `commit_author`

## fixture 来源
`client`、`H`、`svc`(把 `svc.works.viewers` 里的心跳时刻往前拨、再 `sweep()` 一次,模拟超时和后台清理)。
