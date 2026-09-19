# services/work —— 做事层

work 树、画布、会话(现场)、谁动过、round、事件、收件箱(设计:[work.md](../../../../docs/designs/v5/work.md)、[session.md](../../../../docs/designs/v5/session.md))。记录全走 `WorkRepo`,不进 git。`__init__.py` 的 `WorkService` 是门面,其余每个文件管一种记录:

| 文件 | 重点 |
|---|---|
| `__init__.py` | `WorkService(store, work_servers)`:树 `create` / `get` / `forest` / `update`(done 要求子 work 全完;结束后 `_freeze` 冻结会话)/ `search`;画布 `get_canvas` / `put_canvas`;会话 `attach(work_id, uri)`(登记 → 找 server 建现场 → 建不起来就撤登记 → 记 cwd → 进画布第一列)/ `reattach` / `list_sessions`(带 alive)/ `detach`(销毁现场 + 删登记 + 出画布)/ `capture` / `rounds`(先从把手同步新 round);`touch` / `list_users`;`read_inbox` / `manager_of` / `set_manager` / `_deliver`;`history` |
| `tree.py` | `WorkTree`:节点的 CRUD 和状态机(`_transition`),`forest()` 读时拼 `WorkNode`;`WorkNotFound` / `WorkConflict` |
| `canvas.py` | `CanvasStore`:`get` / `put`(version 乐观锁;列 id、会话不能重复)/ `place(session)`(进第一列末尾,没有列就建 `c1`)/ `remove(session)` |
| `sessions.py` | `SessionRegistry`:会话登记的唯一权威,`add`(id = `<work_id>-s<n>`)/ `get` / `list` / `replace` / `touch` / `remove`;`SessionNotFound` |
| `users.py` | `WorkUserRegistry`:`touch(work_id, user)` 记一笔,`list()` 算出 `current`(最近 120 秒)和 `history` |
| `rounds.py` | `Rounds`:`read` / `sync(fresh)`(只追加没见过的 round) |
| `events.py` | `Events`:`emit(work_id, type, **data)` / `read` —— work 自己的 append-only 时间线 |
| `inbox.py` | `Inbox`:`read` / `put` / `put_unmanaged` —— manager.json 路由过来的变动 |
| `repo.py` | `WorkRepo` 接口:`get_work` / `put_work` / `list_works`;每个 work 下的小文档 `get_doc` / `put_doc` / `del_doc`(canvas / sessions / users / manager);流 `append` / `read`(events / inbox / rounds);`append_unmanaged`。`FsWorkRepo`(`works/<id>/…`)+ `DbWorkRepo`(`works` / `work_docs` / `work_logs` 表);`make_work_repo(store)` |
