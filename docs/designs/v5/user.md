# user —— 人:谁建的、谁在动、谁定的(v5 设计)

> **状态:框架稿,部分已实现(原 member 机制)。** 本篇把「人」立成一个概念:**user**。它出现在三处——work 是谁**建**的、work 现在谁**在动 / 动过**、collections 里每个提交是谁**做的**。它**不做权限**:整个实例给一个团队用,团队内不限制。原来叫 member 的那套「谁在操作 / 操作过某个 work」的可见性记录,并入本篇,名字统一叫 user。字段见 [`../../structure/v5/work.md`](../../structure/v5/work.md),端点见 [`../../api/v5/works.md`](../../api/v5/works.md)。

相关:
- v5 work(user 归属挂在 work 上): [work.md](work.md)
- v5 collections(每个提交的 author 就是 user): [collections.md](collections.md)
- v5 session(现场——和 user 是两个词:session 是在哪干活,user 是谁在干活): [session.md](session.md)
- v5 manager(manager 是 work,不是 user;收件箱里每条变动记着是哪个 user 造成的): [manager.md](manager.md)

---

## 1. 一句话:user 是团队里的一个人,系统里到处记着「谁」

一个 memory.talk 实例是**给一个团队用的**。同一棵 work 树、同一份认知层,团队里的人都在上面干活。于是每个对象都有一个自然的问题:**这是谁的、谁在动、谁定的**。user 就是这个「谁」。

它不是一个要先注册的账号,是**在系统里出现过的一个名字**:第一次带着这个名字操作,它就存在了。三处会记它:

| 在哪 | 记什么 | 回答的问题 |
|---|---|---|
| **work** | `created_by`:谁建的(归属,不变);`users`:谁动过、最近什么时候(可见性) | 这件事是谁的?现在谁在弄?以前谁做过? |
| **collections** | 每个 commit 的 author = 做这个动作的 user | 这条认知是谁写的?这个立场是谁提的?这张卡是谁改的? |
| **收件箱** | 每条变动的 `by` | 打到我这的这条,是谁造成的? |

---

## 2. work 有归属:created_by

一个 work 是**谁建的**,建的那一刻定下,不改。这是 work 唯一的归属字段——它回答「这件事是谁的」,但**不是权限**:别人照样能动它、能拆它、能把它做完(§4)。

归属的用处:

- **找人**:一件事做到一半,该问谁——先问建它的人。
- **看视图**:「我的 work」= `created_by` 是我的;「团队在做什么」= 所有 work 按 `created_by` 分。
- **子 work 默认继承父的归属**吗——**不**。谁建的子 work 就是谁的;拆事的人和做事的人可以不同,这正是团队协作的样子。

---

## 3. work 上谁在动:users

work 上还记一份名单:**谁动过这个 work、第一次和最近一次什么时候、动了几次**。「当前正在动」不是一个状态位,是「最近一小段时间内动过」现算出来的。这是原来 member 机制的全部内容,只是名字改叫 user:

- **什么算动**:任何带身份的、会动这个 work 的请求——建、改目标 / 状态、重排画布、开 / 重入 / 关一个 session、打开 work 本身。外加一个显式心跳,给前端「我还开着这个页面」用。
- **粒度是 work**,不细到 session:同一个 tmux 会话多人 attach 本来就是镜像,谁在敲由 tmux 自己解决。
- **两个视图**:`current` = 最近 N 秒内动过的人(先定 2 分钟);`history` = 动过的所有人,按最近活动倒序。人不需要登出,不动就自然掉出 current。
- **用处**:防止两个人同时往一个 agent 会话里敲字;知道该去问谁。

`created_by` 和 `users` 的关系:建 work 的人自动是 `users` 里的第一个;之后谁动谁进名单。`created_by` 永远不变,`users` 一直长。

---

## 4. 不做权限:团队内不限制

这是本篇最重要的一条边界。**所有 work 谁都能操作,所有 collections 谁都能写**;user 只是让人看得见,不是门。

- 没有 owner-only、没有 assignee、没有「只有 X 能改」。想接手别人的 work,直接动;名单上多一个名字,别人一看就知道。
- 没有登录。身份是客户端**自报**的(请求头 `X-Memory-Talk-User`),服务端不校验、不拒绝。团队内互相信任,自报够用;真到了需要鉴权的那天,换成从登录态取名字,user 这层一行不用改。
- 不带身份的请求照样能操作,只是不记名——commit author 退回服务配置的默认名,work 的 `created_by` 为空。

为什么这样定:权限系统的成本是永远的,每个端点都要判、每种角色都要维护;一个团队用一个实例,这些成本换不来什么。**看得见就够了**;看得见还出问题,那是沟通问题,不是权限问题。

---

## 5. collections 里的 user:就是 git author

collections 的每个动作是一个 commit;做这个动作的 user 就是 commit 的 **author**——不是 trailer 里的一个字段,是 git 自己那个 author。于是:

- `git log layer/issue` 一眼看到每个立场、每条论证是谁提的;`git blame` 一张卡,每一行是谁写的。
- 「这条认知是谁定的」不需要在对象里再记一个字段——对象里不存 user,历史里有。
- 没带身份的提交,author 是服务配置的默认名(`MEMORY_TALK_AUTHOR`),等于「匿名」。

和 work 那边对上:work 的 `created_by`、`users` 里的名字,和 commit author 用的是**同一个名字**(请求头里那个),所以「这件事谁在做」和「这个结论谁下的」能对得上。

---

## 6. 边界:user 不是什么

- **不是 session。** session 是现场(在哪干活),user 是人(谁干活)。一个 user 可以开很多 session,一个 session 只被一个 work 拥有、但可以被多个 user attach。
- **不是 manager。** manager 是 work,不是人——变动打给一个 work 的收件箱,由那个 work 里的 agent 或人去推。要知道「那个 work 里是谁」,看它的 `users`。
- **不是 agent。** agent 是在 session 里跑的程序,它的产出记在它所在 work 的名下;agent 做的 collections 提交,author 是**驱动它的 user**(请求头里那个),不是 agent 的名字。要区分「人写的还是 agent 写的」,看提交 body 里的 `Work:`(在哪个 work 的会话里做的)——本篇不给 agent 单独立身份,列在 §7。

---

## 7. user 是顶层对象:有自己的 API 和命令

user 和 work、collections 平级,所以它有自己的面——不是挂在 work 下面的一个子资源:

- **API**:`GET /api/users`(所有出现过的 user,从 work 的 `created_by` / `users` 和 collections 的 commit author 汇总,按最近活动倒序)、`GET /api/users/{name}`(建的 / 动过的 work、最近的提交)、`GET /api/users/me`(请求头里那个名字对应的 user)。
- **CLI**:`memory.talk user list | show <name> | whoami`。
- **汇总,不注册**:没有 users 表、没有建 user 的端点;一个名字出现在任何一处,它就在清单里。这和 §1 说的「在系统里出现过的一个名字」是一回事。服务配置的默认 author(匿名提交)不算 user。

## 8. 这篇有意不定的事

- **身份从哪来**:现在是请求头自报。前端要不要让人第一次打开时填个名字存本地;将来接了登录态,是替换还是叠加。
- **要不要有 user 清单**:现在 user 只是散落在各处的名字,没有一份「团队里有谁」的表。倾向先不要——从 work 的 `users` 和 git author 里能汇总出来;真要头像、邮箱、显示名,再加 user 资料这一类记录(存哪由仓储 + [provider.md](provider.md) 定)。
- **git author 的邮箱**:只有名字时邮箱填什么——倾向 `<名字>@memory.talk`,稳定且可辨认。
- **agent 要不要单独立身份**:agent 的提交现在挂在驱动它的 user 名下。如果实践里「这是人定的还是 agent 定的」真成了问题,再给 agent 一个可辨认的 author(比如 `alice+codex`)。
- **活跃窗口 N**:2 分钟是拍的,跟前端心跳间隔一起调。
- **history 要不要衰减**:一个 work 活几个月,名单上可能有十几个人。先不管。
