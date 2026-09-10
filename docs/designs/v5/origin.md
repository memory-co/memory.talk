# origin —— 事实层:外部来的东西先落在这里,它是地板(v5 设计)

> **状态:框架稿,未实施。** 本篇在 Collections 里再加一个内置的 layer:**origin**。外部来的各种东西——文档、网页、别人给的材料、导出的聊天记录——还没被消化成 issue 或 card 之前,先原样放在这里。它是 Collections 的**最下层**,collectbase 意义上的事实层:上层引用它、改不动它。总定位见 [README.md](README.md)。

相关:
- v5 collections(层即 layer;本篇补上此前缺的那块「地板」): [collections.md](collections.md)
- v5 collections layer(层怎么定义——origin 也照这套,只是它是内置的、最底的): [collections-layer.md](collections-layer.md)
- v5 issue / card(消化 origin 的去处;它们的出处指回 origin): [issue.md](issue.md) / [card.md](card.md)
- v5 store(work 的痕迹是裸文件,不在 Collections——它和 origin 的边界见 §6): [collections-store.md](collections-store.md)
- collectbase 的事实层(只读、`chmod a-w`、智能体不写): [DESIGN.md §1](https://github.com/memory-co/collectbase/blob/main/docs/v2/DESIGN.md)

---

## 1. 一句话:origin 是认知层的地板

[collections.md §4](collections.md) 曾说:memory.talk 的 Collections 里没有 collectbase 意义上的「事实层」——最底下是 issue,而 issue 已经是推论(争的过程)了。现在补上:

```
上   card       ← 争完的结论
     issue      ← 争的过程
下   origin     ← 事实:外部来的、原样的、还没消化的东西。地板。
```

**origin 里的东西不是 memory.talk 想出来的,是从外面来的**:一份设计文档、一个网页、同事发来的一段话、从别的工具导出的会话记录、人写下的一条约束。它们进来的时候**原样**放着——不改写、不总结、不判断;消化它们(读、标注、提问题、写卡)是上层的事。

它就是 collectbase 说的那块「智能体够不着的地板」:**无论上层怎么迭代,重新推导的原料永远是这份没被动过的原文**。

---

## 2. 为什么要有它

三个理由:

- **认知要有地板。** issue 的论证说「证据在这」,card 说「这是事实」——「这」得指向一个不会被上层改掉的东西。没有 origin,它们只能指向 work 的 rounds(裸文件,不在 git 里、没有层的保护)或者互相指(推论指推论,正是 collectbase 说的「记忆腐烂」那条回路)。
- **外部材料得有地方放。** 现在一份外来的文档要么被塞成一张卡(那就把「材料」当成了「断言」),要么丢在 work 目录里(不进 git、没人管、做完就冻结)。都不对。它该有自己的位置,而且是最底的位置。
- **collectbase 的分层语义才完整。** 有了事实层,「上层改不动下层」才真正保护到东西:改 card 碰不到 issue,改 issue 碰不到 origin——推论怎么改,原文都在。

---

## 3. 什么进 origin:外部的、原样的、未消化的

| 进 | 例子 |
|---|---|
| 文档 | 设计稿、规范、README、会议纪要、别人写的分析 |
| 网页 / 文章 | 抓下来的正文(HTML 转文本),附 URL 和抓取时间 |
| 别人给的材料 | 一段聊天、一封邮件、一份截图(二进制走 blob 外置) |
| 导出的会话记录 | 从别的工具带过来的对话(不是本实例 work 里跑出来的——那些见 §6) |
| 人写下的给定 | 「这个项目必须用 Python 3.12」这类不需要争的约束——**注意它是原文,不是卡**;卡是消化后写的 |

三条判据,缺一不进:**外部来的**(不是本实例的推论)、**原样的**(不改写)、**还没消化的**(或者消化了也留着——见 §5)。

不进 origin 的:memory.talk 自己产生的任何东西(issue、card、决定、摘要)——那些是上层;work 的过程痕迹(rounds、屏幕、事件)——那些是裸文件(§6)。

---

## 4. 只读:上层改不动,agent 不写

origin 是最底层,享受 collectbase 给底层的全部保护:

- **文件 444。** 上层写它的那一刻 `EACCES`;`[issue]` / `[card]` 提交碰了任何 origin 路径(不带层后缀的文件或目录),hook 当场拒绝。
- **agent 不写 origin。** 谁写:人(手动放材料)、采集(抓网页、同步外部工具)、导入。agent 在 work 里跑,它的产出是上层的事;它想「修正」一份原文,只能在上层另写一份注解引用它——原文永远在,谁在什么时候提出异议是可 diff 的(collectbase §2 的三个后果,原样成立)。
- **可以删,不可以改。** 一份材料放错了、过期了,可以删(一次 `[origin]` 提交,git 留着);但不改它的内容——改了就不是原文了。

> 「事实」在这里的意思是「**这份东西确实是这样来的**」,不是「它说的是对的」。origin 不评分、不判真伪;一份错的文档也是原样放着,上层去争它对不对(那就是一个 issue)。

---

## 5. 消化:origin → issue → card,origin 不动

材料进来之后的路,就是 v5 已有的那条:

```
origin(原文)──逐段标注、#问题──▶ issue(问题 + 立场 + 论证,evidence 指回 origin)──争完──▶ card(事实,出处指回 origin)
```

- **消化不消耗 origin。** 一份文档被读完、提了三个 issue、写了两张卡,它本身还在原处,一字不动。card 的出处、issue 的证据都指向它——地板就是拿来被指的。
- **「还没消化的」是一份清单,不是一个状态。** 没有任何 issue / card 引用的 origin 对象,就是待读材料;读没读过不写在它身上(它是只读的),从引用关系反推。
- **新材料进来,有人会知道。** 材料所在文件夹的 `manager.json` 绑着一个 work(常常就是管这个主题的那个),每份新进的 origin 都打到它的收件箱([manager.md](manager.md));它去标注、提问题。想让某个来源的东西专门由某个 work 消化,给那个来源单独一个文件夹、放一个 `manager.json`。

---

## 6. 边界:origin 和 work 的痕迹

work 的 rounds、屏幕、事件是**本实例自己的过程**,它们是裸文件、不进 git([collections-store.md §4](collections-store.md))。origin 收的是**外部来的**。两者都是「事实」,但一个是过程、一个是材料,分开放:

| | work 的痕迹(`works/<id>/…`) | origin(Collections 里不带层后缀的一切) |
|---|---|---|
| 从哪来 | 本实例的 agent 会话跑出来的 | 外面来的 |
| 体量 | 大、持续增长、每一轮都记 | 一份一份的,进来就定 |
| 要不要「为什么」 | 不要,它就是流水 | 要:来源、时间、谁放的 |
| 在不在 git | 不在 | 在,最底层 |
| 谁引用 | issue 的 `origin` / `evidence` 指 `(work_id, rounds)` | issue 的 `evidence`、card 的出处指 origin 对象 |

一段 round **值得长期当证据**(比如「基准跑出来就是这个数」),而它所在的 work 做完就冻结、不进 git——那就把那几轮**摘录**一份放进 origin:一个 origin 对象,`source` 写明来自哪个 work 的哪几轮,内容原样复制。这是唯一一种「本实例产生的东西进 origin」——因为它已经不是推论,是被选出来当证据的原文。

> issue 里那个叫 `origin` 的字段(「从哪个 work 的哪些 round 冒出来」)和这一层同名,不是巧合:它们说的都是**出处**。字段指向 work 的 rounds 或指向 origin 层的对象,两种都行;长期要留的,走后者。

---

## 7. 形态:没限制,文件或目录都行

origin **没有形态约束**:Collections 目录树里任何**不带层后缀**的文件或目录,都是 origin。一份 markdown、一个 PDF(软链到 blob)、一个装着十几个文件的文件夹——放进来就是。

```
memory.talk/
├── manager.json
└── 配置/
    ├── 旧的 settings 方案.md                    ← origin:一个文件
    ├── 同事发来的截图.png → ../../blob/…        ← origin:二进制外置,原地留软链
    ├── 上个季度的调研/                          ← origin:一个目录,里面随便放
    │   ├── 访谈记录.md
    │   └── 数据.csv
    ├── 该走文件还是环境变量.issue/              ← 不是 origin:带后缀
    └── 配置只来自环境变量.card/                 ← 不是 origin:带后缀
```

meta 是**可选的**:想记「从哪来、什么时候、谁放的」,在旁边放一个 `<名>.origin.json`(或目录里放 `origin.json`),字段只有 `source` / `kind` / `fetched_at` / `by`。不写也行——文件本身就是事实,git 记着谁什么时候放进来的。**没有** summary、tags、rating:那些是消化的产物,归上层。

不分目录、不分来源、不分类——**怎么摆是人的事**,按主题摆,让原文和它的讨论页、词条待在一起。

---

## 8. 层序里的位置

```
layers:  origin, issue, card           ← origin 永远第一个(最底)
```

按 [collections-layer.md §2](collections-layer.md) 的规则「引用谁就排在谁上面」:所有层都会引用 origin(它是出处),没有层被 origin 引用,所以它在最底。用户自定义的层同样排在它之上。

---

## 9. 这篇有意不定的事

- **rounds 摘录的粒度**(§6):按轮、按段、还是整个会话;摘录要不要保留工具调用的原始输出。
- **去重**:同一份文档两次进来(抓两次网页、两个人各放一份)——按内容哈希合并,还是各放各的、让上层引用其中一份。倾向后者:origin 不做聪明事,重复也是事实。
- **大材料**:一本 200 页的 PDF 进 origin,是整本(blob)+ 抽出的文本,还是只抽文本。倾向两者都留:原件 blob、文本 content。
- **采集器**:谁把网页抓成 origin、谁把外部工具的会话同步进来——是 memory.talk 的一部分,还是外部脚本直接往 Collections 里 commit(`[origin]`)。collectbase 说「不做采集」;倾向 memory.talk 先只提供「放进来」的端点,采集是外部的。
- **过期**:材料旧了要不要标。不标——它是原文,旧也是事实;上层的 card 说「这条已过时」。
