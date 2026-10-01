# works / viewers — 现在谁在看这个 work

## 这个场景在测什么
`works.viewers`(`docs/designs/v5/work-store.md §3`):心跳只在进程内存里(work → 人 → 最后一次心跳),`viewers` 是它整份算出来的投影(按名字排)。
建 work 的人、打开 work(`GET /works/{id}`)、`POST /users/touch` 都算心跳;`GET /users` 只剩 `current`(名字列表);
`POST /users/leave` 立刻拿掉;超过窗口(120 秒)没心跳的被清出去;重启(再起一个 app)所有 work 的 `viewers` 清空;看不进轨迹。

## 不在这测什么
- 谁做过什么(轨迹里的 `user.id`)→ `works/trace`
- user 的活动统计(`active_works` 等)→ `users/activity`

## fixture 来源
`client` / `svc` / `H`;超时用 `svc.works.viewers` 里的心跳时刻往前拨。
