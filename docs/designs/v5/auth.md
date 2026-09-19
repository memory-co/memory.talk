# auth —— 先立 admin,再进门(v5 设计)

> **状态:定稿,已有实现。** [user.md](user.md) 把「谁」立成注册的实体,并且说过:「真到了需要鉴权的那天,换成从登录态取名字,user 这层一行不用改」。这一篇就是那一天。服务一旦挂到公网上,自报身份就不够了——本篇加两样东西:**setup**(没有 `admin` 账号时,先设 admin,别的什么都不能做)和**登录**(密码换 token,之后每个请求都带)。**权限仍然只有一档**:admin 管账号,其他的谁都能动——[user.md §4](user.md#4-不做权限团队内不限制) 的边界不变,只是「你是谁」从自报变成了证明。

相关:
- [user.md](user.md):user 的档案、归属、author,这一篇只是把「名字从哪来」换掉
- [`../../api/v5/auth.md`](../../api/v5/auth.md):端点
- [`../../cli/v5/README.md`](../../cli/v5/README.md):`memory.talk setup / login / logout`

---

## 1. 一句话:没有 admin 就先建 admin;有了之后,没登录什么都看不到

服务起来之后,任何请求先过一道门(`main.py` 里的一个中间件),按顺序回答两个问题:

1. **有 `admin` 这个账号吗?** 没有 → 除了 `GET /api/auth/status` 和 `POST /api/auth/setup`,全部 409 `setup_required`。前端看到这个状态就只显示 **setup 页**:设 admin 的密码(可带显示名、邮箱),设完自动登录进去。这一步只能做一次——`admin` 一旦存在,`setup` 就 404。
2. **带了有效 token 吗?** 没带、或 token 不认识 → 401 `unauthorized`。前端看到 401 就清掉本地登录态,显示 **登录页**。

门之外的只有:`/`(前端页面本身)、`/assets`(静态资源)、`/api/auth/status`、`/api/auth/setup`、`/api/auth/login`、`/api/system/health`。其余 `/api/*` 一律要 token。

## 2. 账号:user 加两个字段

user 还是 [user.md](user.md) 那个注册的实体,存的地方不变(fs `users/<name>.json` / db `users` 表),多两个字段:

| 字段 | 说明 |
|---|---|
| `role` | `admin` / `member`。`admin` 这个名字的账号 role 固定是 admin;别的都是 member |
| `password` | 密码的哈希,存的 `scrypt$<salt>$<hash>`(标准库 `hashlib.scrypt`,不引依赖);**任何接口都不返回它**。空 = 这个人还不能登录,等 admin 给设 |

admin 能做而 member 不能做的,只有三件:**建账号**(`POST /api/users`,带初始密码)、**给别人设密码**(`PUT /api/users/{name}/password`,不用旧密码)、**改别人的档案**。member 只能改自己的档案、改自己的密码(要旧密码)。除此之外没有权限差别:work 谁都能建能动,collections 谁都能写——那是团队内的事,不是门的事。

## 3. token:随机串,服务端记着,注销即失效

登录 = `POST /api/auth/login {name, password}` → 返回一个 token(`secrets.token_urlsafe(32)`)。服务端只存它的 sha256(fs `auth/tokens/<sha256>.json` / db `auth_tokens` 表),记着是谁的、什么时候发的。之后每个请求 `Authorization: Bearer <token>`;`POST /api/auth/logout` 删掉它。不设过期——一个团队的实例,token 泄露了就 logout 或换密码(换密码会把这个人的 token 全部作废)。

**身份从 token 来,不再从请求头 `X-Memory-Talk-User` 来。** 这个头现在被忽略:名字由中间件解析 token 得到,塞进 `request.state.user`,controller 从那里取。user.md 里三处记「谁」的地方(work 的 `created_by` / `users`、collections 的 commit author、收件箱的 `by`)一行没改,只是名字的来源换了。匿名不再存在:能进门的都有名字。

## 4. 客户端

- **网页**:进来先问 `GET /api/auth/status` → `{setup_required, authenticated, user}`。`setup_required` → setup 页;没登录 → 登录页;登录了 → 正常的壳。token 存浏览器本地(和语言、侧栏折叠放一起),每个请求带上;任何一个请求 401 就回登录页。设置页里:改自己的显示名 / 邮箱 / 密码、退出登录;admin 多一块「团队成员」——建账号、给人设密码。原来那个「选一个身份」的单选没有了,身份就是登录的人。
- **CLI**:`memory.talk setup`(首次,设 admin 密码)、`memory.talk login [--user <名字>]`(问密码,token 存到 `~/.memory.talk/credentials.json`,按服务地址分开记)、`memory.talk logout`。之后所有命令自动带 token;也可以 `MEMORY_TALK_TOKEN` 环境变量直接给。`--user` / `MEMORY_TALK_USER` 只用来挑存的是哪个人的凭据,不再自报身份。
- **agent 会话里**:tmux 里跑的 agent 要调 API,得有 token——给它 `MEMORY_TALK_TOKEN`(比如 admin 专门 login 一次,把 token 放进 workspace 的环境)。服务端**不**自动把开会话那个人的 token 塞进会话环境;这是有意的:浏览器的登录态不该出现在一个 shell 里。

## 5. 不做什么

- 不做过期、刷新、多因素、OAuth。团队实例,登录态就是一个可撤销的随机串。
- 不做细粒度权限。仍然是 user.md 的判断:看得见就够了。
- 不做 HTTPS。挂公网请自己在前面放反代;token 明文走 HTTP 等于没有门。
