# services/work —— 做事层

work 树、画布、工作单元(现场)、谁动过、round、事件、收件箱(设计:[work.md](../../../../docs/designs/v5/work.md)、[worklet.md](../../../../docs/designs/v5/worklet.md))。记录全走 `WorkRepo`,不进 git。`__init__.py` 的 `WorkService` 是门面,其余每个文件管一种记录:

| 文件 | 重点 |
|---|---|
| `__init__.py` | `WorkService(store, work_servers)`:树 `create` / `get` / `forest` / `update`(done 要求子 work 全完;结束后 `_freeze` 冻结工作单元)/ `search`;画布 `get_canvas` / `put_canvas`;工作单元 `attach(work_id, uri)`(登记 → 找 server 建现场 → 建不起来就撤登记 → 记 cwd → 进画布第一列)/ `reattach` / `list_worklets`(带 alive)/ `detach`(销毁现场 + 删登记 + 出画布)/ `rounds`(先从把手同步新 round);`touch` / `list_users`;`read_inbox` / `manager_of` / `set_manager` / `_deliver`;`history` |
| `tree.py` | `WorkTree`:节点的 CRUD 和状态机(`_transition`),`forest()` 读时拼 `WorkNode`;`WorkNotFound` / `WorkConflict` |
| `canvas.py` | `CanvasStore`:`get` / `put`(version 乐观锁;列 id、工作单元不能重复)/ `place(worklet)`(进第一列末尾,没有列就建 `c1`)/ `remove(worklet)` |
| `worklets.py` | `WorkletRegistry`:工作单元登记的唯一权威,`add`(id = `<work_id>-w<n>`)/ `get` / `list` / `replace` / `touch` / `remove`;`WorkletNotFound` |
| `users.py` | `WorkUserRegistry`:`touch(work_id, user)` 记一笔,`list()` 算出 `current`(最近 120 秒)和 `history` |
| `rounds.py` | `Rounds`:`read` / `sync(fresh)`(只追加没见过的 round) |
| `events.py` | `Events`:`emit(work_id, type, **data)` / `read` —— work 自己的 append-only 时间线 |
| `inbox.py` | `Inbox`:`read` / `put` / `put_unmanaged` —— manager.json 路由过来的变动 |
| `repo.py` | `WorkRepo` 接口:`get_work` / `put_work` / `list_works`;每个 work 下的小文档 `get_doc` / `put_doc` / `del_doc`(canvas / worklets / users / manager);流 `append` / `read`(events / inbox / rounds);`append_unmanaged`。`FsWorkRepo`(`works/<id>/…`,子 work 在父目录的 `subs/<id>/` 下,目录就是树;id → 目录懒扫索引)+ `DbWorkRepo`(`works` / `work_docs` / `work_logs` 表);`make_work_repo(store)` |
