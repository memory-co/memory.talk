# services —— 业务逻辑的分层与思路

每个子包对应一篇设计([`docs/designs/v5/`](../../../docs/designs/v5/README.md));入口是子包的 `__init__.py`(导出 `XxxService`),其余文件是内部实现。细节在代码里,这里只说整体思路。

```
controllers ──▶ services ──▶ providers(介质原语)
                  │
                  ├── collections/   认知层:分层 git 仓库
                  │     git.py        git 原语(只跟命令行说话,不认识层)
                  │     repo.py       分层拓扑:layer/* 权威分支 + stack 合并视图 + 路径归属守卫 + collections.json 锚定
                  │     manager.py    manager.json:目录绑 work,最近祖先解析
                  │     __init__.py   CollectionsService:层的装载(内置 + 用户层)、对象读写(一批文件改动 → 层的 check → 一个提交)、历史、检索、树、投递
                  ├── work/          做事层:work 树、画布、会话(现场)、users(谁动过)、round、事件、收件箱
                  │     repo.py       WorkRepo 业务接口 + fs 版 / db 版两份实现
                  ├── users/         人:注册的实体,档案走仓储;活动统计从 work 与 collections 现算
                  ├── work_servers/  现场怎么建:tmux 基类、agent 基类(把手多一项读 round)、注册表、URI 解析、各平台会话记录 adapter
                  └── store/         装配:按 MEMORY_TALK_STORE 选 provider,按族建 work / user 仓储
```

## 三条主线

**1. 认知层是 git,不是数据库。** `collections/` 把一个 git 仓库做成分层记录:每层一条 `layer/<名>` 分支只放自己的文件,`stack` 是各层的并集视图。一个动作就是一个 `[层] …` 提交,先落到层分支、再在 stack 上打一个 merge 节点。跨层的决定(争出结果写卡、对卡开讨论页)是两个相邻提交带同一个 trailer。守卫在写入时:路径按后缀 / 机制规则该归哪层、是否已被别的层占——不符即拒。历史、检索、旧版本都直接问 git(`log` / `grep` / `show`)。根上的 `collections.json` 是唯一锚定:有哪些层、什么顺序、用户层的 schema,它的提交历史就是层的变化史。`git.py` 和 `repo.py` 分开:前者是原语,换一种拓扑不用动它;后者是拓扑,不关心怎么调 git。

**2. 现场层是记录,介质可换。** `work/` 和 `users/` 的记录(work 节点、画布、会话登记、谁动过、round、事件、收件箱、user 档案)是业务对象,不进 git。业务层只认仓储接口(`WorkRepo` / `UserRepo`);仓储按 provider 的**族**各实现一份——文件系统版整文件读写,数据库版走链式查询——同一族之内换介质(LocalFS → S3、SQLite → MySQL)仓储不动。`store/` 负责装配。

**3. 现场怎么建,协议自己说。** `work_servers/` 里每个 work server 声明自己响应哪些协议,没人声明的协议去 default(协议名当命令名在 tmux 里跑);寻址在 attach 时内部发生,调用方只看到窗和把手。agent 类 server 比终端多一项把手能力:从平台自己的会话记录里读 round,追加进 work 的 rounds 流——这是 work 留给认知层的原料。

## 三层之间怎么接

- **work → collections**:work 的 round 是 issue 的原料(逐 round 标注,未实现);issue 的出处、论证的证据指回 `(work_id, rounds)`。
- **collections → work**:目录下的 `manager.json` 把这一片的变动投递到某个 work 的收件箱;work 树的父子是隐式的 manager 链。
- **user 贯穿两边**:work 记谁建的、谁动过;collections 的 commit author 就是 user;仓储和 provider 对它一视同仁。

## 约定

- service 之间只通过构造函数注入(`main.py` 装配),不互相 import 对方的内部模块。
- 错误是各自的异常类(`CollectionsError` / `WorkNotFound` / `UserExists` …),由 `main.py` 统一映射成 `Result` 信封里的 `error` 码;service 不认识 HTTP。
- 不做权限:身份只校验「注册过没有」。
