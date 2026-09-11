# user

人。和 work、collection 平级的顶层对象;**不注册、不做权限**——在系统里出现过的名字就是 user。对应 [`/api/users`](../../api/v5/users.md)。机制见 [`../../designs/v5/user.md`](../../designs/v5/user.md)。

```
memory.talk user
├── list                 # 所有出现过的 user,按最近活动倒序
├── show <name>          # 一个 user:建的 / 动过的 work、最近的提交
└── whoami               # 我是谁(--user / MEMORY_TALK_USER),以及我的 work 和提交
```

## user list

```
alice   建 3 / 动 5 个 work   12 次提交   正在动 work_…2f2f   最近 2 分钟前
bob     建 0 / 动 2 个 work    4 次提交                       最近 1 小时前
```

汇总自 work 的 `created_by` / users 名单和 collections 的 commit author;服务默认 author(匿名提交)不算。

## user show

```bash
memory.talk user show bob
```

建的 work、动过的 work(各带状态)、最近 20 条 collections 提交(sha / 时间 / subject)。不存在的名字 → exit 1。

## user whoami

`--user` / `MEMORY_TALK_USER` 对应的 user 的 `show`;没设 → 提示怎么设,exit 2。名字是新的(还没出现过)→ 打印名字和「还没做过任何事」。
