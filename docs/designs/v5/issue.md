# issue —— 一个问题一个目录:readme.md 是主题,positions/ 一个立场一个文件,links.yaml 放边(v5 设计)

> **状态:设计稿,代码未跟上。** 现在代码里 issue 是一个 `issue.json`,立场、论证、出处、卡全嵌在里面;本篇改成**多文件目录**,并且把 issue 和 work / card 的耦合解开:issue 不再记 `origin`、不再记 `card`,只管问题、立场、论证和 issue 之间的边。改完后 [structure collections.md](../../structure/v5/collections.md) 和 `layers/issue.py` 跟着改。总定位见 [README.md](README.md)。

相关:
- collections(issue 是一个 layer;对象是任意位置的 `<名>.issue/` 目录): [collections.md](collections.md)
- manager(目录下的 `manager.json` 决定谁管它——这是 issue 和 work 之间**唯一**的机制耦合): [manager.md](manager.md)
- card(卡引用 issue;issue 不引用卡): [card.md](card.md)
- v4 问题图(IBIS 三节点 + 边,本篇机制的来源): [../v4/card.md](../v4/card.md)

---

## 1. issue 是什么

一个**问题**,底下挂几个**立场**(候选答案),每个立场挂**论证**(支持 / 反对 / 中立,一句话,可提证据)。这是 IBIS。work 是做,card 是记,issue 是**议**:还没定的事待在这里。

issue 不关闭、立场只增不改、立场之间靠论证竞争、沉默不算数——沿用 v4,§5 说。

---

## 2. 形态:一个目录,几个文件

```
memory.talk/配置/该走文件还是环境变量.issue/
├── readme.md             ← 主题:问题的展开。纯 markdown,没有 frontmatter;标题就是目录名
├── links.yaml            ← 和别的 issue 的边
├── positions/
│   ├── p1.md             ← 一个立场:# 主张 + 阐述 + ## 论证;普通 markdown
│   └── p2.md
└── manager.json          ← 谁管它(机制文件,见 manager.md;可无)
```

**目录名就是问题。** `该走文件还是环境变量` 既是路径的末段,也是这个 issue 的标题;不在文件里再写一遍 `question`。目录 / 检索 / 收件箱里显示的都是它。

**为什么拆成多个文件:**

- **变动落在该落的地方。** 加立场 = 新建一个文件;给某个立场加论证 = 改那一个文件;连一条边 = 改 `links.yaml`。`git log -- positions/p2.md` 是 p2 的全部历史,`git diff` 一眼看出改了哪个立场。
- **立场是竞争的单位,也是文件的单位。** 两个人同时给不同立场加论证,碰的是不同文件。
- **人能直接读写。** `cat readme.md` 就是问题,`ls positions/` 就是有几个立场。
- **冷热分开。** `readme.md` 建了基本不动;`links.yaml` 偶尔加一行;`positions/` 是活跃的那一半。

### readme.md

```markdown
背景:v5 起服务时要读 home、store 类型、tmux socket 这几样……

边界:只讨论服务进程自己的配置;各 work server 的配置不算。
```

就是问题的展开——背景、为什么冒出来、边界。**没有 frontmatter,没有字段。** 可以为空(只有目录名的 issue 也合法:一个还在等答案的问题)。可以改,历史在 git。

### links.yaml

```yaml
- {type: specializes, target: memory.talk/配置/配置怎么管}
- {type: suggested_by, target: memory.talk/架构/该不该拆服务#p2}
```

一个列表,每项 `{type, target}`;`target` 是对端 issue 的 path(`suggested_by` 可带 `#<position_id>`)。同 `(type, target)` 不重复;只增。没有边就没有这个文件。

`type` ∈ `specializes`(本 issue 是 target 的子问题)/ `suggested_by`(被 target 引出)/ `questions`(质疑 target 的前提)/ `replaces`(重述并取代 target)/ `related`。

**只连 issue。** 和 work、和 card 的关系不在这里(§4)。

### positions/<id>.md

```markdown
# 只用环境变量,不要配置文件

为什么这么主张,前提是什么。

## 论证

- +1 试了一遍,环境变量够用(work_try#9)
- -1 本地开发要改十几个变量,太烦
```

**普通 markdown,没有 frontmatter。** 一级标题就是主张(claim),下面是阐述;论证是 `## 论证` 下的一个列表,一条一行,行首 `+1` / `0` / `-1` 是立场,后面是一句话,证据顺手写在括号里(一个 work 的 round、一个 origin 路径、一个 URL,系统不解析)。

谁、何时——不在文件里,在 git:每个立场一次提交、每条论证一次提交,`git log -- positions/p1.md` 就是这个立场的完整记录,author 和 date 都在,提交信息还带着方向(`argue <path>#p1 +1`)。

| 部分 | 改不改 | 说明 |
|---|---|---|
| id(文件名) | 不改 | `p<n>`,issue 内顺序编号 |
| `# 标题` | 不改 | 主张。改主意是加新立场,不是改旧的 |
| 阐述 | 建时写 | 之后要补充,走论证 |
| `## 论证` 列表 | 只增 | 一条一行,append 到末尾 |

**读视图现算**:每个立场数 `## 论证` 下 `+1` / `-1` / `0` 开头的行 → `up / down / neutral`,`credence = up - down`;`GET` 一个 issue 把 `readme.md`、`links.yaml`、`positions/*.md` 合起来给,立场按 credence 倒序。不存、不回写。

### 对 layer 机制的要求

issue 从「一个本体文件」变成「一个目录里的一组文件」:`readme.md` 和 `positions/*.md` 都是无 frontmatter 的普通 markdown,`links.yaml` 是一个 YAML 列表。layer 的形态描述([collections-layer.md](collections-layer.md))要能表达「目录型对象,由几种文件组成」。标题来自目录名,不来自字段。守卫不用改:`.issue/` 下的一切本来就归 issue 层。

---

## 3. 行为:每个行为碰哪个文件

| 行为 | payload | 碰的文件 | 提交信息 |
|---|---|---|---|
| 建 issue(通用 create) | 正文?(可空) | 新建 `readme.md` | `[issue] write <path>` |
| 改展开(通用 update) | 正文 | 改 `readme.md` | `[issue] edit <path>` |
| `position` | `claim`, 正文? | 新建 `positions/p<n>.md`(`# claim` + 正文) | `[issue] position <path>#p<n>: <claim>` |
| `argue` | `position`, `stance`, `comment`(证据写在 comment 里) | 改 `positions/p<n>.md`(`## 论证` 下追加一行) | `[issue] argue <path>#p<n> +1` |
| `link` | `type`, `target` | 改 / 新建 `links.yaml`(追加一条) | `[issue] link <path> <type> <target>` |

就这三个行为。「只增不改」由行为保证(`argue` / `link` 只 append),层守卫兜底(`[card]` 提交碰不到 `.issue/`)。

---

## 4. issue 和别的东西:弱耦合

这个版本里 issue **不记**它从哪个 work 冒出来,**不记**它写成了哪张卡,**不记**为它派了哪些 work。理由:这些都是别人的事,记在 issue 里就把 issue 和 work / card 的生命周期绑死了——work 冻结了、卡删了,issue 里留着一个悬空的引用。

| 关系 | 谁记 | 怎么记 |
|---|---|---|
| issue 从哪个 work 冒出来 | 不记 | 要追,看提交 author 和 manager work 的 rounds |
| 谁管这个 issue | `manager.json` | 目录下放一个,或继承上级目录的([manager.md](manager.md))。这是 issue 和 work 之间**唯一**的机制耦合,而且是「目录归谁管」,不是 issue 的字段 |
| 论证的证据在哪 | 论证那一行的文字 | 自由格式,系统不解析、不校验 |
| issue 争出的卡 | **card 记**:`card.md` 的 `issue` 字段指向这个 issue | 写卡是 card 层的一次 create;issue 这边不动 |
| 对卡不同意开的讨论页 | **card 记**:同上 | 建 issue + 改卡的 `issue` 字段,两个提交,card 层的行为 |
| issue 之间 | `links.yaml` | §2 |

所以原来 issue 上的 `decide` / `spawn` 行为、`Decision:` / `Discussion:` trailer 在这个版本**都不要**:写卡就是写卡,派 work 就是派 work,各自在各自的层做,想关联就在 card 的 `issue` 字段或论证那一行里写一句。

---

## 5. 竞争规则(沿用 v4)

- 立场之间靠论证竞争,credence 现算,不钉状态。
- issue 不设「已解决」;多个立场长期并存合法;没有立场的 issue 也合法。
- 立场只增不改;改主意加新立场。
- 沉默不算数:没碰到这个 issue 的 work 不给任何立场加减分。
- manager 不能拍板;它能做的是让论证多起来。

---

## 6. 有意不定的事

- **新 issue 默认谁管**:倾向不自动写 `manager.json`,靠所在文件夹的继承链。
- **立场文件的正文能不能事后改**:目前定「建时写、之后走论证」;若发现阐述常要修,再放开。
- **论证要不要结构化**:现在是 `## 论证` 下一行一条,靠行首 `+1 / 0 / -1` 认方向;谁、何时靠 git。若以后要按证据检索,再考虑结构化。
