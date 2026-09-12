# issue —— 一个问题一个目录:issue.md 是主题,positions/ 里一个立场一个文件(v5 设计)

> **状态:设计稿,代码未跟上。** 现在代码里 issue 是一个 `issue.json`,立场和论证全嵌在里面;本篇把它改成**多文件目录**:`issue.md` 放问题和边,`positions/<id>.md` 一个立场一个文件,论证挂在各自立场的文件里。改完后 [structure collections.md](../../structure/v5/collections.md) 和 `layers/issue.py` 跟着改。总定位见 [README.md](README.md)。

相关:
- work(issue 的原料来源、manager 所在、派活的去处): [work.md](work.md)
- collections(issue 是一个 layer;对象是任意位置的 `<名>.issue/` 目录): [collections.md](collections.md)
- manager(目录下的 `manager.json` 决定谁管它): [manager.md](manager.md)
- card(争完写成卡;issue 是卡的讨论页): [card.md](card.md)
- v4 问题图(IBIS 三节点 + 边,本篇机制的来源): [../v4/card.md](../v4/card.md)

---

## 1. issue 是什么

一个**问题**,底下挂几个**立场**(候选答案),每个立场挂**论证**(带证据的支持 / 反对)。这是 IBIS。work 是做,card 是记,issue 是**议**:还没定的事待在这里,争到某个立场站住,写成 card。

issue 不关闭、立场只增不改、立场之间靠论证竞争、沉默不算数——这四条沿用 v4,§5 说。

---

## 2. 形态:一个目录,几个 markdown

```
memory.talk/配置/该走文件还是环境变量.issue/
├── issue.md              ← 主题:问题、出处、写成的卡、和别的 issue 的边(links)
├── positions/
│   ├── p1.md             ← 一个立场:主张、出处、派出的 work、论证
│   └── p2.md
└── manager.json          ← 谁管它(机制文件,见 manager.md)
```

**为什么拆成多个文件,而不是一个 JSON:**

- **变动落在该落的地方。** 加一个立场 = 新建一个文件;给某个立场加论证 = 改那一个文件;连一条边 = 改 `issue.md`。`git log -- positions/p2.md` 就是 p2 这个立场的全部历史,`git diff` 一眼看出改了哪个立场,不用在一个大 JSON 里找。
- **立场是竞争的单位,也是文件的单位。** 两个人同时给不同立场加论证,碰的是不同文件,不冲突。
- **人能直接读写。** 目录里就是几个 markdown,`cat` 出来是可读的;agent 不经 API 也能看懂一个 issue 现在争到哪了。
- **变得少的和变得多的分开。** `issue.md` 建了以后基本不动(边偶尔加,`card` 决定时写一次);`positions/` 是活跃的那一半。

### issue.md

```markdown
---
question: 配置该走文件还是环境变量?
origin: {work_id: work_a, rounds: [3, 4]}
card: memory.talk/配置/配置只来自环境变量
links:
  - {type: specializes, target: memory.talk/配置/配置怎么管}
  - {type: suggested_by, target: memory.talk/架构/该不该拆服务#p2}
created_at: 2026-09-12T02:00:00Z
---

问题的展开:背景、为什么冒出来、边界在哪、哪些不算这个问题。
```

| 字段 | 改不改 | 说明 |
|---|---|---|
| `question` | 不改 | 问题本身;也是标题 |
| `origin` | 不改 | 从哪冒出来:work 的哪些 round,或 origin 层的一个路径。**出处不是归属** |
| `card` | 改 | 争完写成的卡的 path(`decide` 写入),或这个 issue 挂在哪张卡上当讨论页(`discuss` 写入) |
| `links[]` | 只增 | 和别的 issue 的边,`{type, target}`;同 `(type, target)` 不重复。**边在 issue.md 里,不在立场里** |
| `created_at` | 不改 | |
| 正文 | 可改 | 问题的展开。改它不改问题(`question` 不动) |

`links.type` ∈ `specializes`(本 issue 是 target 的子问题)/ `suggested_by`(被 target 引出,target 可写 `<path>#<position_id>`)/ `questions`(质疑 target 的前提)/ `replaces`(重述并取代 target)/ `related`。`target` 是对端 issue 的 path。

### positions/<id>.md

```markdown
---
claim: 只用环境变量,不要配置文件
origin: {work_id: work_a, rounds: [4]}
spawned_works: [work_try]
arguments:
  - {id: a1, stance: 1, comment: 试了一遍,环境变量够用, evidence: {work_id: work_try, rounds: [9]}, work_id: work_try, by: alice, at: 2026-09-12T03:00:00Z}
  - {id: a2, stance: -1, comment: 本地开发要改十几个变量,太烦, by: bob, at: 2026-09-12T04:00:00Z}
created_at: 2026-09-12T02:10:00Z
---

立场的阐述:为什么这么主张,前提是什么。
```

| 字段 | 改不改 | 说明 |
|---|---|---|
| id(文件名) | 不改 | `p<n>`,issue 内顺序编号 |
| `claim` | 不改 | 主张。改主意是加新立场,不是改旧的 |
| `origin` | 不改 | 这个立场从哪来 |
| `spawned_works[]` | 只增 | 为验证它派出的 work id |
| `arguments[]` | 只增 | 论证:`stance` 1 / 0 / -1,`comment` 一句话,`evidence` 证据在哪(Origin),`work_id` 若来自派出的论证 work,`by` 谁说的,`at` 何时 |
| `created_at` | 不改 | |
| 正文 | 建时写 | 立场的阐述。之后要补充,走论证 |

**读视图现算**:每个立场 `up / down / neutral` = `stance` 为 1 / -1 / 0 的论证数,`credence = up - down`;`GET` 一个 issue 把 `issue.md` 和 `positions/*.md` 合起来给,立场按 credence 倒序。不存、不回写。

### 对 layer 机制的要求

issue 从「一个本体文件」变成「一个目录里的一组文件」。layer 的形态描述([collections-layer.md](collections-layer.md))要能表达:本体 `issue.md` + 附属 `positions/*.md`,都是 markdown + YAML frontmatter(**完整 YAML**,不再限于 `key: value` 一行)。守卫不用改:`.issue/` 目录下的一切本来就归 issue 层。历史:`git log -- <path>.issue/` 是这个问题的全部,`-- positions/p2.md` 是一个立场的。

---

## 3. 行为:每个行为碰哪个文件

行为是 schema 之上的领域动作,统一签名 `(collections, path, payload, ctx)`;每个行为一个 `[issue]` 提交,信息如下。

| 行为 | payload | 碰的文件 | 提交信息 |
|---|---|---|---|
| 建 issue(通用 create) | `question`, `origin?`, 正文? | 新建 `issue.md` | `[issue] write <path>` |
| `position` | `claim`, `origin?`, 正文? | 新建 `positions/p<n>.md` | `[issue] position <path>#p<n>: <claim>` |
| `argue` | `position`, `stance`, `comment?`, `evidence?`, `work_id?` | 改 `positions/p<n>.md`(追加一条) | `[issue] argue <path>#p<n> +1` |
| `spawn` | `position`, `work_id` | 改 `positions/p<n>.md`(追加) | `[issue] spawn <path>#p<n> -> <work_id>` |
| `link` | `type`, `target` | 改 `issue.md`(追加一条边) | `[issue] link <path> <type> <target>` |
| `decide` | `position`, `card`, `title?`, `body?` | 改 `issue.md`(写 `card`)+ **另一个提交** `[card] write <card>` | 两个相邻提交,同一个 `Decision:` trailer;第二个失败第一个反向退回 |
| 被 `card.discuss` 开成讨论页 | (card 的行为) | 新建 `issue.md`(`card` 指回那张卡)+ **另一个提交** `[card] link` | 同一个 `Discussion:` trailer |

「只增不改」由行为保证(`argue` 只会 append),层守卫兜底(`[card]` 提交碰不到 `.issue/`)。

---

## 4. issue 和 work

**从哪来**:主入口是 work 的痕迹——逐 round 标注里 `#` 出来的问题拿去检索,没着落就建 issue,撞上老问题就挂上去(答案落成立场,证据落成论证)。是不是新问题由检索判定,不由 agent 自评。也可以直接手建。`origin` 记出处,出处不是归属。

**谁管**:目录下的 `manager.json`,或往上最近的一个([manager.md](manager.md))。manager 就是树上正卡在这个问题上的 work;issue 的每次变动打到它的收件箱;它的画布是议这个问题的现场。一路找不到 = 没人管,这是有用的状态。

**派活取证**:一个立场站不站得住常常是做出来的。在 manager work 里为某个立场开一个子 work(`spawn`),做完后它的 rounds 成为那个立场的一条论证(`argue` 带 `work_id` 和 `evidence`)。

| work 的角色 | 跟 issue 的关系 | 留下什么 |
|---|---|---|
| 出处 work | issue 从它的痕迹里冒出来 | `issue.md` 的 `origin` |
| manager work | 绑定给 issue,负责推它 | 议事记录(它的 rounds) |
| 论证 work | 为某个立场取证而开 | `positions/p<n>.md` 里的一条论证 |

三种角色不是三种 work,是同一种 work 跟 issue 的三种关系。反向的路也有:胜出立场直接落成 work 树上的新节点——那是**照着**立场做,不是**为了验**它。

---

## 5. 竞争规则(沿用 v4)

- 立场之间靠论证竞争,credence 现算,不钉状态。
- issue 不设「已解决」;多个立场长期并存合法;没有立场的 issue 也合法。
- 立场只增不改;改主意加新立场。
- 沉默不算数:没碰到这个 issue 的 work 不给任何立场加减分。
- manager 不能拍板;它能做的是派活取证让论证多起来。

---

## 6. issue 图与 issue → card

**图**:`issue.md` 的 `links` 把 issue 连成图(细化、引出、质疑、取代、相关)。issue 图和 work 树是两套层级:树表达事怎么拆,图表达问题怎么细化,靠 manager 对上。不要互相代替。

**→ card**:争出结果就 `decide`——某个立场写成一张 card,`issue.md` 的 `card` 指过去,card 的 `issue` 指回来;两个相邻提交,各在自己的层。写卡不关闭 issue,它继续当讨论页;翻盘就回来改卡。反过来,一张卡有人不同意,`card.discuss` 开一个 issue 挂上去。

---

## 7. 有意不定的事

- **新 issue 默认谁管**:倾向不自动写 `manager.json`,靠所在文件夹的继承链。
- **论证 work 的结果怎么落成论证**:人标方向,还是从 rounds 自动提。
- **立场文件的正文能不能事后改**:目前定「建时写、之后走论证」;若发现阐述常要修,再放开(反正在 git 里)。
- **`arguments` 放 frontmatter 还是正文小节**:frontmatter 好解析、追加是加几行;正文小节更像人写的讨论。先 frontmatter。
