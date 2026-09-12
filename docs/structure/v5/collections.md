# Collections(层、对象、仓库)

认知层的数据模型。机制见 [designs collections.md](../../designs/v5/collections.md);端点见 [api collections.md](../../api/v5/collections.md)。

> issue 和 card 是 Collections 的两个内置 layer,它们的字段就在本篇里(§对象);不再各自单独成篇。

## 仓库:分层 git

```
~/.memory.talk/collections/           一个 git 仓库,自己实现的分层拓扑(语义对齐 collectbase,不依赖它)
  refs/heads/layer/origin        权威分支:只放这一层的文件,线性
  refs/heads/layer/issue
  refs/heads/layer/card
  refs/heads/layer/<用户层>      从始祖出发
  refs/heads/stack               合并视图:每次层提交后一个 merge 节点(parents = [stack, 层提交]),树 = 各层并集
  HEAD → stack;工作树跟着 stack(只为了人能 ls / cat,服务从不读它)
```

- **始祖** = 第一个提交,只有根上的 `collections.json`:`{"version": 1, "layers": [{"name": "origin", "builtin": true}, …]}`,最底在前;用户层的项内嵌 `schema` 和 `added_at`。所有分支从它出发;`git log collections.json` = 层的变化史。
- **一个动作一个提交**,信息以 `[层名]` 开头;跨层的决定是两个相邻提交 + 同一个 trailer。`git log --first-parent stack` 是全部认知的时间线;`git log layer/<层>` 是那一层的。
- **守卫**(写时,plumbing 内):① 后缀 / 机制规则说这个路径该归哪层,和声明的层不符 → 拒;② 路径已在别的层的树里 → 拒。所以 `[card]` 提交碰不到 `.issue/` 里的东西。
- **机制文件**:`collections.json` 归最底层;`manager.json` 归它所在目录按后缀规则算出的层。它们的变动不投递,也不出现在 tree / 目录里。
- 全部 plumbing(hash-object / update-index / write-tree / commit-tree / update-ref),不需要工作树、不装 hook——服务进程是唯一写者。

## 对象:带后缀的目录

| | origin | issue | card | 用户层 `<名>` |
|---|---|---|---|---|
| 形态 | 任何**不带后缀**的文件 | `<path>.issue/` 目录:`readme.md` + `meta.yaml` + `positions/*.md` | `<path>.card/card.md` | schema 的 `files` 清单;单文件简写 = `<path>.<名>/<名>.md` 或 `.json` |
| id | 文件路径 | `path`(不含后缀) | `path` | `path` |
| 格式 | 原文 | markdown / yaml / markdown | markdown + frontmatter | 每个文件各自定 |
| 标题 | 文件名 | 目录名 | `title` | `dirname` 或 `<文件>:<字段>` |
| 层序 | 0(最底) | 1 | 2 | 之上,按 `collections.json` 的 `layers[]` 顺序 |

**层就是这个目录的校验器**:目录里只能有清单上的文件,每个文件按格式和字段校验,一次写整目录过一遍,不过整批拒(422)。对象目录里还可以放 `manager.json`(谁管它,机制文件,不在清单里)。目录树按主题组织,原文、`.issue/`、`.card/` 并排。

### issue 层(内置)

`<path>.issue/` 目录,三种文件;标题就是目录名。机制见 [designs issue.md](../../designs/v5/issue.md)。

```
memory.talk/配置/该走文件还是环境变量.issue/
├── readme.md                          问题的展开;纯 markdown,可空;必需
├── meta.yaml                          可无
├── positions/
│   ├── 只用环境变量,不要配置文件.md     文件名 = 主张;阐述 + `## 论证` 下一行一条
│   └── 走配置文件,环境变量只做覆盖.md
└── manager.json                       机制文件,可无
```

**meta.yaml**

```yaml
links:
- {type: specializes, target: memory.talk/配置/配置怎么管}
positions:                     # manager 的判定:排前面的当前占优;claim 必须是 positions/ 下已有的文件
- {claim: 只用环境变量,不要配置文件, note: 试过了,够用}
summary: 目前倾向只走环境变量
```

| 键 | 改不改 | 说明 |
|---|---|---|
| `links[]` | 只增 | `{type, target}`;`type` ∈ `specializes` / `suggested_by` / `questions` / `replaces` / `related`;`target` 是对端 issue 的 path(`suggested_by` 可带 `#<主张>`);同 `(type, target)` 不重复 |
| `positions[]` | 可改 | `{claim, note?}`,按占优程度从前到后 |
| `summary` | 可改 | 一句总结 |

**positions/<主张>.md**:普通 markdown,无 frontmatter;文件名非空、不含 `/`;`## 论证` 之后的列表行是论证,一行一条,不打分。谁、何时在 git(`git log -- positions/<主张>.md`)。

**读视图**:`{"readme", "positions": [{"claim", "note", "body", "arguments": [...]}], "links", "summary"}`;立场按 `meta.positions` 排,没排到的按文件名。不算 credence。

没有 `origin` / `card` 字段:issue 不记它从哪来、不记写成了哪张卡(卡记 issue)。没有 id:id 就是 path;立场没有 id:主张就是文件名。

### card 层(内置)

`<path>.card/card.md`。维基式事实条目:可改、可删,历史在 git;**没有分数、没有状态位**。机制见 [designs card.md](../../designs/v5/card.md)。

```markdown
---
title: 配置只来自环境变量
context: memory.talk v5
links: memory.talk/配置/另一张卡
issue: memory.talk/配置/该走文件还是环境变量
---

只用环境变量。配置文件是多出来的一份状态,要同步。
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `title` | string | 维基式规范标题——它出现在目录里,召回靠它 |
| `context` | string | 在哪成立:关于哪个项目 / 用户 / 场景。「本地论」在卡上的落法——不是治理字段,是事实陈述的一部分 |
| `links[]` | string[] | 相关卡的 path(内链,只有一种类型) |
| `issue` | string \| null | 讨论页:挂在这张卡上的 issue 的 path |
| `body` | string | 正文,可以比一句话长;但**一张卡讲一件事** |

frontmatter 是 YAML(`links` 是列表);空值不写;多余的键拒。读出来是 `{"title", "context", "links": [...], "issue", "body"}`。没有 `status`:删就是删,历史在 git;没有 id:id 就是 path。

### 用户层的 schema

写成 YAML 交给 `POST /api/collections/layers`,系统把它嵌进 `collections.json` 的 `layers[]`。两种写法:

```yaml
layer: experiment                  # 目录清单:每个文件一条,路径可用 * 通配
title: dirname                     # 或 <文件>:<字段>
files:
  readme.md:   {format: markdown, required: true}
  result.yaml: {format: yaml, fields: {verdict: {type: string, required: true}, issue: {type: ref, layer: issue}}}
  "runs/*.md": {format: markdown}
```

```yaml
layer: decision                    # 单文件简写:目录里只有 decision.md
format: markdown+frontmatter       # 或 json
title: title
fields:
  title:    {type: string, required: true}
  rejected: {type: "list[string]"}
  issue:    {type: ref, layer: issue}
```

格式:`markdown` `markdown+frontmatter` `yaml` `json` `text`;字段类型:`string` `int` `bool` `"list[string]"` `ref` `"list[ref]"`。markdown+frontmatter 自动带 `body`。没有行为。

## manager.json

```json
{"work": "work_…"}
```

放在任何目录(含对象目录)下。解析:路径往上找最近的一个。变动投递到那个 work 的 `works/<work>/inbox.jsonl`:

```json
{"ts": "…", "layer": "issue", "path": "<对象 path>", "subject": "position …", "sha": "…", "by": "alice", "routed_by": "memory.talk"}
```

`routed_by` 是哪个目录的 `manager.json`('' = 根);work 层过来的是 `"parent"` 或那个 work 的 id。没人管 → `~/.memory.talk/unmanaged.jsonl`。
