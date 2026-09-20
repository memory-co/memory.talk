# manager —— manager.json:目录绑 work,变动打过去,work 干活(v5 设计)

> **状态:框架稿,未实施。** 本篇立 manager 机制的大框架:任何一个目录下都可以放一个 `manager.json`,把这个目录(连同它下面的一切)绑到一个 work;目录里的东西一有变动,变动就打到那个 work,那个 work 就干活、把事情往下推。它取代 [issue.md §3](issue.md) 里「issue 上一个 `manager_work` 字段」的做法——从单个对象的字段,变成目录级、可继承的文件。字段 / 端点后续分篇。总定位见 [README.md](../README.md)。

相关:
- v5 work 树(manager 绑的是 work;父子本身就是一条隐式的 manager 链): [work.md](../work.md)
- v5 issue(原来的 `manager_work` 字段由本篇取代): [issue.md](issue.md)
- v5 metas(认知层的目录在 git 里,「变动」= 触碰这些路径的 commit): [README.md](README.md)
- v5 user(manager 是 work 不是人;谁在那个 work 里干活看它的 users): [user.md](../user.md)

---

## 1. 一句话:一个文件,把「这里的变动」交给「那个 work」

```
memory.talk/manager.json                              {"work": "work_…root"}   ← 这个主题文件夹里的一切(原文、讨论页、词条)
memory.talk/配置/该走文件还是环境变量.issue/manager.json  {"work": "work_…db"}     ← 单独管这一个 issue
works/work_…a1/manager.json                           {"work": "work_…root"}   ← 一棵 work 子树
```

`manager.json` 就一句话:**这个目录归那个 work 管**。它下面任何东西变了——一张卡被改、一个 issue 多了一条论证、一个子 work 做完了——变动就**打到**绑定的 work 那里;那个 work 里跑着的 agent(或人)看到变动,决定下一步:该写卡就写卡,该派活就派活,该推进父 work 就推进。

manager 机制**只保证一件事:变动一定会落到某个会干活的 work 手里**。至于干什么活,是那个 work 的事。

---

## 2. 为什么是目录级的文件,不是对象上的字段

issue.md 原来的做法是每个 issue 记一个 `manager_work`。它有三个不够:

- **只能管一个对象。** 「memory.talk 这个项目的所有卡」「所有还没人管的 issue」这种一片东西,得一个个绑。
- **只有 issue 有。** card 改了没人管,work 子树做完了没人管——「谁来接着推」这件事对每一层都成立,不该只在 issue 上有。
- **绑定藏在对象里。** 看一眼目录不知道谁在管;换 manager 要改对象本身。

改成**目录下一个文件**,三个问题一起解掉:

| | 字段 `manager_work` | 目录里的 `manager.json` |
|---|---|---|
| 作用范围 | 一个对象 | 一个目录及其下所有东西 |
| 谁能有 | 只有 issue | 任何目录:一片卡、一个 issue、一棵 work 子树、整个 Metas |
| 可见性 | 要读对象 | `ls` 就看见;`git log manager.json` 就是换 manager 的历史 |
| 继承 | 无 | 子目录没有就往上找(§3) |

而且它和被管的东西**同处一地**:在 Metas 里它跟着 issue / card 进 git、进那一层;在 work 目录里它是裸文件。不另立一张「谁管谁」的表——**规则和事实是同一份数据**(这句是 collectbase 的原话,在这里同样成立)。

---

## 3. 谁管这里:最近的祖先

一个路径变了,往上找**最近的一个 `manager.json`**,那就是它的 manager:

```
manager.json                                     ← Metas 根:管一切(默认)
memory.talk/manager.json                         ← 管这个主题文件夹;比上一个近,优先
memory.talk/配置/配置只来自环境变量.card/card.md    ← 变了 → 打到 memory.talk/manager.json 绑的 work
memory.talk/配置/旧的 settings 方案.md             ← origin 变了(新放进来)→ 同上,同一个 work
其他/某张卡.card/card.md                          ← 变了 → 没有更近的 → 打到根 manager.json 绑的 work
```

`manager.json` **不分层**:一个主题文件夹里的原文、讨论页、词条,变动都打到同一个 work——这正是把它们摆在一起的意思。

- **根上的 `manager.json` 就是全局默认**——整个 Metas 的「兜底管理者」。
- **一路都没有**:这个变动**没人管**。它不会丢,会进一份「无人管的变动」清单——跟 issue.md 说的「没人管的 issue 是有用的状态」一个意思:看得见哪些地方没人接。
- **work 树里,父子就是隐式的 manager**:一个 work 目录下没有 `manager.json`,它的变动默认打到**父 work**。所以子 work 做完、父 work 收到,这条链不用另外配;放一个 `manager.json` 是为了**改写**这个默认——比如让一棵子树的变动打到另一个专门盯着它的 work。

---

## 4. 什么算变动,怎么「打过去」

**变动**:

| 在哪 | 变动 = | 谁产生 |
|---|---|---|
| Metas(git) | 一个 commit 触碰了这个目录下的路径 | collectbase 的 post-commit 就是天然的信号源;一个 commit 一条变动,带 `[层名]`、动词、路径、trailer |
| work 目录(裸文件) | work 的事件:状态变了、新 session、新 round、做完 | work 层的 events.jsonl 就是信号源 |

**打过去**:变动**投递**到 manager work 的**收件箱**——work 目录下一个 append-only 的 `inbox.jsonl`。每条:什么时候、哪个路径、什么变动、谁干的、以及**它是被哪个 `manager.json` 路由过来的**(便于回答「为什么这事到我这」)。

- 收件箱是 work 的痕迹的一部分,跟 rounds / events 一样只追加、不进 git。
- work 里的 agent 怎么消费收件箱——开工时读一遍、干活中轮询、还是直接推进会话——是 [work-server.md §7](../work-server.md) 那条「把手要不要开驱动」的问题,本篇不定;**最小形态是收件箱 + agent 自己去读**。
- **manager work 自己造成的变动不投递给自己**:它写了一张卡,这张卡的变动路由回它自己——跳过,否则自激。变动记「谁干的」(git author / work 的 session)就能判。

---

## 5. work 收到之后干什么:不规定,但有几个典型

manager 机制不规定动作。但把它接到 v5 已有的几条线上,会自然长出这些:

| 收到的变动 | manager work 典型会做的 |
|---|---|
| issue 多了一条论证 | 看看某个立场站住了没;站住了就**写卡**(`[issue] decide` + `[card] write`) |
| issue 冒出来、没人管 | 绑到自己(写一个 `manager.json`),或**派出**一个论证 work 去取证 |
| 一张卡被改 | 检查链接到它的卡和 issue 有没有过时;有争议就开讨论页 |
| 子 work 做完 | 看兄弟节点完了没;都完了推进父 work 的状态,或写下一步的子 work |
| 一片卡里加了新卡 | 更新目录 / 合并重复的卡 |

这些都是「把事情往下做」——manager work 是**在推进**,不是在**审批**。它没有比别人更大的权限(user.md:不做权限),只是变动先到它这里、它先动手。

---

## 6. 跟现有设计的关系

| | 之前 | 有了 manager 之后 |
|---|---|---|
| issue 的 `manager_work` 字段 | issue 上一个字段;`PUT /api/issues/{id}/manager` 改它 | **退役**。issue 目录下的 `manager.json` 取代;绑 / 换 / 解绑 = 写 / 改 / 删这个文件(一次 `[issue]` 提交) |
| `GET /api/issues?manager_work=` / `unmanaged=` | 按字段过滤 | 按 `manager.json` 解析:「这个 work 管哪些 issue」= 所有路由到它的 issue;「没人管」= 一路找不到 `manager.json` |
| issue.md §4 派出论证 work | `positions[].spawned_works` | 不变——派出是 issue 的领域动作,不是 manager 机制的事;派出的 work 默认挂在 manager work 下 |
| work 树的父子 | 只表达「事怎么拆」 | 同时是**隐式的 manager 链**:子的变动默认打到父 |
| issue / card 的存储形态 | `issues/<id>.json`、`cards/**/<slug>.md`,按层分目录 | 都变成**带后缀的目录**,放哪都行:`<名>.issue/issue.json`、`<名>.card/card.md`,自己目录里可放 `manager.json`([metas.md §1](README.md)) |
| collectbase 分层 | `[issue]` / `[card]` 各自路径 | `manager.json` 是**机制文件**(同 `metas.json`),不是证据:在 `.issue/` 里随 `[issue]` 提交,在 `.card/` 里随 `[card]` 提交,在普通文件夹里归最底层但**不受 444 保护**——memory.talk 把它登记为机制例外 |

---

## 7. 这篇有意不定的事

- ~~单文件对象要不要变目录~~:已定——issue、card 都是带后缀的目录([metas.md §1](README.md)),自己身上就能放 `manager.json`;origin 文件或目录都行,管它就管它所在的文件夹。
- **投递形式**:收件箱(拉)还是推进会话(推)。§4 按收件箱写;推的那半等把手开驱动再说。
- **变动粒度**:一个 commit 一条,还是一个「决定」(两个相邻提交)合成一条。倾向按 commit,由消费方自己合并——投递侧不做聪明事。
- **`manager.json` 里还要不要别的**:现在只有 `work`。要不要 `only: ["argue", "write"]` 这类过滤、要不要 `until`(临时代管)——先不要,一个字段起步。
- **无人管的变动放哪**:一份全局的 `unmanaged.jsonl`,还是根 `manager.json` 缺省指向一个「收容 work」。倾向前者——「没人管」应该显眼,不该被一个默认 work 吞掉。
- **循环**:A 目录绑 work X,X 的目录绑 work Y,Y 的目录绑 X……变动会不会在两个 work 之间弹。§4 的「自己造成的不投给自己」挡一层;两个 work 互相投的情况要不要限跳数,等真出现。
