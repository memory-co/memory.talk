# services/users —— 人

user 是注册的顶层实体(设计:[user.md](../../../../docs/designs/v5/user.md)):档案是存的,活动统计是现算的。身份从登录态来(`services/auth`),这里不管密码校验,只在建账号时把哈希写进记录。

| 文件 | 重点 |
|---|---|
| `__init__.py` | `UserService(repo, work_repo, metas)`:`register(req)`(`admin` 这个名字 role 固定 admin;密码哈希进记录)/ `get` / `exists` / `update`(整条记录改字段再放回,不丢密码)/ `author(name)`(commit author 的名字 + 邮箱,空邮箱用 `<name>@memory.talk`)/ `list()`(`UserView`,按最近活动倒序)/ `profile(name)`(`UserProfile`:建的 / 动过的 work、最近 20 条提交)/ `search(q)`。`_activity()` 从 work 记录和 `git log` 现算每个人的统计。`UserNotFound` / `UserExists` 映射成 404 / 409 |
| `repo.py` | `UserRepo` 接口 + `FsUserRepo`(`users/<name>.json`)+ `DbUserRepo`(`users` 表);`make_user_repo(store)` |
