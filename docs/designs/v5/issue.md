# issue —— 一个问题一个目录:readme.md 是问题,positions/ 一个立场一个文件;每个文件 = 字段 + 正文(v5 设计)

> **状态:已实施。** `layers/issue.yaml` 就是这一层的协议:两种文件(`readme.md`、`positions/<主张>.md`),各自的字段和正文;引擎按它校验,前端按它出表单。没有行为,写就是写文件。API / CLI 见 [api collections.md](../../api/v5/collections.md) / [cli collection.md](../../cli/v5/collection.md),文件形态见 [structure collections.md](../../structure/v5/collections.md)。总定位见 [README.md](README.md)。

相关:
- collections(issue 是一个 layer;对象是任意位置的 `<名>.issue/` 目录): [collections.md](collections.md)
- manager(目录下的 `manager.json` 决定谁管它——issue 和 work 之间**唯一**的机制耦合;也是谁来判定排序): [manager.md](manager.md)
- card(卡引用 issue;issue 不引用卡): [card.md](card.md)
- v4 问题图(IBIS 三节点 + 边,本篇结构的来源;v4 的 credence 现算在 v5 不用了): [../v4/card.md](../v4/card.md)

---

## 1. issue 是什么

一个**问题**,底下挂几个**立场**(候选答案),每个立场底下是围绕它的**论证**(一行一条的讨论)。work 是做,card 是记,issue 是**议**:还没定的事待在这里。

哪个立场当下占优,**不靠计数**,靠管这个 issue 的 work 看过论证之后做判断,写进每个立场自己的 `rank` / `verdict` 字段,整体的一句总结写进 `readme.md` 的 `summary`;判断可以随时改,历史在 git。

---

## 2. 形态:一个目录,两种文件

```
memory.talk/配置/该走文件还是环境变量.issue/
├── readme.md             ← 问题:字段(links / summary)+ 正文(问题的展开);标题就是目录名
├── positions/
│   ├── 只用环境变量,不要配置文件.md     ← 一个立场:文件名就是主张;字段(links / rank / verdict)+ 正文(阐述 + ## 论证)
│   └── 走配置文件,环境变量只做覆盖.md
└── manager.json          ← 谁管它(机制文件,见 manager.md;可无)
```

**目录名就是问题,文件名就是主张。** `该走文件还是环境变量` 既是路径末段也是标题;`positions/只用环境变量,不要配置文件.md` 的文件名就是这个立场的主张。都不在文件里再写一遍,也没有 `p1` 这种编号。

**每个文件 = 字段 + 正文。** 字段在 frontmatter,正文在下面;像 Notion 里的一行,上面是属性,下面是内容。没有单独的元数据文件,也没有「关于别的文件的表」:一个立场的边、排名、判语就在它自己头上,和正文一起提交、一起有历史。

**为什么拆成多个文件:**

- **变动落在该落的地方。** 加立场 = 新建一个文件;给某个立场加论证、改它的排名 = 改那一个文件;改总结 = 改 `readme.md`。`git log -- positions/<主张>.md` 是一个立场的全部历史,包括它的地位怎么变的。
- **立场是文件的单位。** 两个人同时给不同立场加论证,碰的是不同文件。
- **人能直接读写。** `cat readme.md` 是问题和总结,`ls positions/` 是有几个立场,`head` 一个立场就是它的排名和判语。
- **冷热分开。** `readme.md` 的正文建了基本不动,字段偶尔改;`positions/` 是活跃的那一半。

### readme.md

```markdown
---
links:
  - {type: specializes, target: memory.talk/配置/配置怎么管}
  - {type: suggested_by, target: memory.talk/架构/该不该拆服务#先拆成两个服务}
summary: 目前倾向只走环境变量;等 work_try 把 .env 那条路验完再定。
---

背景:v5 起服务时要读 home、store 类型、tmux socket 这几样……

边界:只讨论服务进程自己的配置;各 work server 的配置不算。
```

| 部分 | 改不改 | 说明 |
|---|---|---|
| `links[]` | 只增 | 和别的 issue 的边,`{type, target}`;`type` ∈ `specializes`(本 issue 是 target 的子问题)/ `suggested_by`(被 target 引出)/ `questions`(质疑 target 的前提)/ `replaces`(重述并取代 target)/ `related`;`target` 是对端 issue 的 path(可带 `#<主张>` 指到对端的某个立场) |
| `summary` | 可改 | 对整个 issue 现状的一句总结(manager 写) |
| 正文 | 可改 | 问题的展开——背景、为什么冒出来、边界。可以为空(只有目录名的 issue 也合法) |

`summary` 和各立场的 `rank` / `verdict` 是**判断**,不是计算:由 manager work 里的人或 agent 读完论证之后写下来。改了就是一次 `[issue]` 提交(一次可以改几个立场的 `rank`,一个提交)。

### positions/<主张>.md

`positions/只用环境变量,不要配置文件.md`:

```markdown
---
rank: 1
verdict: 试过了,够用;本地开发的痛点用 .env 解
links:
  - {type: depends_on, target: memory.talk/配置/本地开发怎么给配置}
---

为什么这么主张,前提是什么。

## 论证

- 试了一遍,环境变量够用(work_try#9)
- 本地开发要改十几个变量,太烦
- 可以配一个 .env 文件给本地用,服务本身还是只读环境变量
```

**文件名是主张,字段是它的排名、判语和它与别处的关系,正文是阐述 + 论证。** `## 论证` 下一行一条讨论——支持也好、反对也好、补一个证据也好,就是一句话,**不打 +1 / -1**。证据顺手写在括号里(work 的 round、origin 路径、URL,系统不解析)。

谁、何时——在 git:每个立场一次提交、每条论证一次提交,`git log -- positions/<主张>.md` 就是这个立场的完整记录。

| 部分 | 改不改 | 说明 |
|---|---|---|
| 文件名 | 不改 | 主张本身。改主意是加新立场,不是改旧的(也不重命名) |
| `rank` | 可改 | manager 的判定:数字越小越靠前;空 = 未判定。读的时候按 `rank` 升序、再按文件名;重复和空洞不校验 |
| `verdict` | 可改 | 为什么排这,一句话 |
| `links[]` | 可改 | 这个立场和别的 issue(或对端的某个立场)的关系:`supports` / `refutes` / `depends_on` / `related` |
| 正文 | 可改 | 阐述 + `## 论证` 列表(一条一行,加在末尾)。协议不锁正文;「不改旧论证、改主意加新立场」是约定,历史在 git |

### issue 层 = 一份协议

规则不在代码里,在 `issue.yaml`([collections-layer.md §2](collections-layer.md)):两种文件、各自的字段和正文、哪个必需。引擎按它校验,前端按它出表单。落到规则就是:

| 文件 | 规则 |
|---|---|
| `readme.md` | 必需;不能删;字段只能是 `links` / `summary`,`links[].type` 五选一;正文随便改 |
| `positions/*.md` | 新建随意(文件名非空、不含 `/`);字段只能是 `links` / `rank` / `verdict`;正文随便改 |
| `manager.json` | 机制文件,系统的,任何层都允许,不进校验 |
| 其他任何文件 | **拒** |

一次提交里几个文件一起校验,一个不过整批不落。标题来自目录名。

---

## 3. 写:每个动作碰哪个文件

没有行为,没有专门的端点。做任何事都是「往目录里提交文件」,协议决定过不过;提交主题由调用方给(`subject`),不给就是 `write / edit <path>`。

| 动作 | 碰的文件 | 建议的提交主题 |
|---|---|---|
| 建 issue | 新建 `readme.md`(字段可空、正文可空) | `write <path>` |
| 改展开 | 改 `readme.md` 正文 | `edit <path>` |
| 加立场 | 新建 `positions/<主张>.md`(阐述) | `position <path>: <主张>` |
| 加论证 | 改 `positions/<主张>.md`,`## 论证` 下多一行 | `argue <path>#<主张>: <一句话>` |
| 连边 | 改 `readme.md` 的 `links`(或某个立场的 `links`) | `link <path> <type> <target>` |
| 排序 | 改一个或几个立场的 `rank` / `verdict`(一次 put,一个提交) | `rank <path>: <首位主张>` |
| 总结 | 改 `readme.md` 的 `summary` | `summarize <path>` |

协议只管形状(有哪些文件、哪些字段);「不改旧论证、改主意加新立场」是约定不是校验——反正历史在 git,改了看得见。层守卫兜底(`[card]` 提交碰不到 `.issue/`)。

---

## 4. issue 和别的东西:弱耦合

这个版本里 issue **不记**它从哪个 work 冒出来,**不记**它写成了哪张卡,**不记**为它派了哪些 work。这些都是别人的事,记在 issue 里就把 issue 和 work / card 的生命周期绑死了。

| 关系 | 谁记 | 怎么记 |
|---|---|---|
| issue 从哪个 work 冒出来 | 不记 | 要追,看提交 author 和 manager work 的 rounds |
| 谁管这个 issue、谁来判定排序 | `manager.json` | 目录下放一个,或继承上级目录的([manager.md](manager.md))。这是 issue 和 work 之间**唯一**的机制耦合,而且是「目录归谁管」,不是 issue 的字段 |
| 论证的证据在哪 | 论证那一行的文字 | 自由格式,系统不解析 |
| issue 争出的卡 | **card 记**:卡的 `readme.md` 字段里 `issue` 指向这个 issue | 写卡是 card 层的一次 create;issue 这边不动 |
| 对卡不同意开的讨论页 | **card 记**:同上 | 建一个 issue,再改卡的 `issue` 字段;两个普通提交,各在自己的层 |
| issue 之间 | `readme.md` 的 `links`;立场和别处的关系在立场自己的 `links` | §2 |

原来的 `decide` / `spawn` / `discuss` 行为、`Decision:` / `Discussion:` trailer、`/act/` 端点在这个版本**都不要**。

---

## 5. 谁占优:判定,不计数

v4 用 +1 / -1 累成 credence 现算排序,v5 不这么做。理由:论证的分量不等,数条数没意义;而且这个 issue 本来就有人管——manager work 在推它,读完论证做个判断是它的本职。所以:

- **排序是 manager 的判断**,写在每个立场自己的 `rank` / `verdict` 里;改了留历史。
- **issue 不设「已解决」**;多个立场长期并存合法;没有立场的 issue、立场都没有 `rank` 的 issue 都合法。
- **改主意加新立场**,不改旧的;这是约定,不是校验。
- **manager 判定的是「当下谁占优」,不是拍板**。要变成事实,去写卡([card.md](card.md));卡指回这个 issue,issue 继续开着当讨论页。

---

## 6. 有意不定的事

- **新 issue 默认谁管**:倾向不自动写 `manager.json`,靠所在文件夹的继承链。
- **立场文件的正文能不能事后改**:目前定「建时写、之后走论证」;若发现阐述常要修,再放开。
- **主张当文件名的长度和字符**:文件名有长度上限、不能含 `/`;主张太长时怎么办(截断?要求短句?)先不定,靠约定「主张是一句短话」。
- **改 `rank` / `verdict` 要不要限定只有 manager work 能做**:现在不做权限(user.md),谁都能改;先靠约定。
