# user

人。和 work、collection 平级的顶层对象,**注册的实体**:有自己的存储(fs 或数据库,走 provider)和档案(名字、显示名、邮箱、角色)。身份来自登录态(`memory.talk login`,见 [README](README.md));权限只有一档:admin 建账号、设密码。对应 [`/api/users`](../../api/v5/users.md)。机制见 [`../../designs/v5/user.md`](../../designs/v5/user.md)、[`auth.md`](../../designs/v5/auth.md)。

```
memory.talk user
├── add    <name> [--display-name '<…>'] [--email <…>] [--password <…>]   # 建账号(admin)
├── list                                                # 所有注册的 user,带活动统计,按最近活动倒序
├── show   <name>                                       # 档案 + 建的 / 动过的 work、最近的提交
├── set    <name> [--display-name '<…>'] [--email <…>]   # 改档案
├── whoami                                              # 当前登录态对应的 show
└── passwd [<name>] [--old-password] [--new-password]   # 改密码:自己的要旧密码;admin 给 <name> 设不用
```

## user add

```bash
memory.talk user add alice --display-name 'Alice' --email alice@example.com --password '…'
```

只有 admin 能建(member → exit 1 `forbidden`)。`name` 是唯一 id(`[A-Za-z0-9_.-]`,最长 64);`--password` 不给就先不能登录,之后 `user passwd alice` 再设。已存在 → exit 1 `exists`。邮箱用作 collection 提交的 author 邮箱,不填则 `<name>@memory.talk`。

## user list

```
alice   Alice   建 3 / 动 5 个 work   12 次提交   正在动 work_…2f2f   最近 2 分钟前
bob             建 0 / 动 2 个 work    4 次提交                       最近 1 小时前
carol           建 0 / 动 0 个 work    0 次提交                       (还没动过)
```

档案是存的;统计是从 work 和 collection 现算的。注册了但没动过的也在。

## user show / set

`show <name>`:档案、建的 work、动过的 work(各带状态)、最近 20 条 collection 提交。不存在 → exit 1。
`set <name> --display-name … --email …`:改档案。

## user whoami

`--user` / `MEMORY_TALK_USER` 对应的 `show`;没设 → 提示怎么设,exit 2;设了但没注册 → exit 1,提示 `user add`。
