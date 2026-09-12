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
| 形态 | 任何**不带后缀**的文件 | `<path>.issue/issue.json` | `<path>.card/card.md` | `<path>.<名>/<名>.md` 或 `.json` |
| id | 文件路径 | `path`(不含后缀) | `path` | `path` |
| 格式 | 原文 | JSON | markdown + frontmatter | schema 定 |
| 标题 | 文件名 | `question` | `title` | schema 的 `title` |
| 层序 | 0(最底) | 1 | 2 | 之上,按 `collections.json` 的 `layers[]` 顺序 |

对象目录里还可以放 `manager.json`(谁管它)和附件。目录树按主题组织,原文、`.issue/`、`.card/` 并排。

### issue 层(内置)

`<path>.issue/issue.json`。问题 + 立场 + 论证 + IBIS 边;立场 / 论证只增不改(行为保证,层守卫兜底)。

> **设计已改**:[designs issue.md](../../designs/v5/issue.md) 把它改成多文件目录——`readme.md`(问题的展开,标题 = 目录名)+ `meta.yaml`(issue 间的边 + manager 对立场的排序和总结)+ `positions/<主张>.md`(一个立场一个普通 markdown,文件名就是主张,论证一行一条、不打分);不再有 `origin` / `card` 字段、不再算 credence,不再有 `decide` / `spawn`。下面是**代码现状**,代码跟上后本节重写。

```json
{"question": "memory.talk v5 的配置该走文件还是环境变量?",
 "origin": {"work_id": "work_a", "rounds": [3, 4], "origin": null},
 "card": "memory.talk/配置/配置只来自环境变量",
 "positions": [
   {"id": "p2", "claim": "只用环境变量,不要配置文件", "origin": null,
    "arguments": [{"id": "a1", "stance": 1, "comment": "试了一遍,环境变量够用",
                   "evidence": {"work_id": "work_try", "rounds": [9]}, "work_id": "work_try", "created_at": "…"}],
    "spawned_works": ["work_try"], "created_at": "…",
    "up": 1, "down": 0, "neutral": 0, "credence": 1}],
 "links": [{"type": "specializes", "target": "memory.talk/配置/更大的那个问题"}],
 "created_at": "…"}
```

**Issue**

| 字段 | 类型 | 改不改 | 说明 |
|---|---|---|---|
| `question` | string | 不改 | 问题本身;也是标题(目录 / 召回用) |
| `origin` | Origin \| null | 不改 | 从哪冒出来:work 的哪些 round,或 origin 层的一个路径。**出处不是归属** |
| `card` | string \| null | 改 | 争完写成的卡的 path(`decide` 写入),或这个 issue 挂在哪张卡上当讨论页(`discuss` 写入) |
| `positions[]` | Position[] | 只增 | |
| `links[]` | IssueLink[] | 只增 | 同 `(type, target)` 不重复 |
| `created_at` | ISO 8601 | 不改 | |

没有 `manager_work` 字段:谁管它看同目录的 `manager.json`。没有 id 字段:id 就是 path。

**Origin**:`{"work_id": "…", "rounds": [int], "origin": "<origin 层路径>"}`,三项都可空;`rounds` 是 `rounds.jsonl` 里的下标。

**Position**

| 字段 | 说明 |
|---|---|
| `id` | `p<n>`,issue 内顺序编号 |
| `claim` | 立场文本 |
| `origin` | 这个立场从哪来(Origin \| null) |
| `arguments[]` | 只增 |
| `spawned_works[]` | 为验证这个立场派出的 work id;去重 |
| `created_at` | |

读视图多四个**现算**字段:`up` / `down` / `neutral` = `stance` 为 `1` / `-1` / `0` 的论证数;`credence = up - down`;立场按 credence 倒序。不存、不回写。

**Argument**

| 字段 | 说明 |
|---|---|
| `id` | `a<n>`,立场内顺序编号 |
| `stance` | `1` 支持 / `0` 中立 / `-1` 反对;`≠0` 的就是 IBIS Argument |
| `comment` | 一句话 |
| `evidence` | Origin \| null:证据在哪 |
| `work_id` | 若来自派出的论证 work,记它 |
| `created_at` | |

**IssueLink**:`{"type", "target"}`。`type` ∈ `specializes`(本 issue 是 target 的子问题)/ `suggested_by`(被 target 引出,target 可写 `<path>#<position_id>`)/ `questions`(质疑 target 的前提)/ `replaces`(重述并取代 target)/ `related`;`target` 是对端 issue 的 path。

**沉默不算数**:没有论证就没有计数;`0` 也不进 credence。

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

frontmatter 只有 `key: value` 行;`links` 逗号分隔;空值不写。读出来是 `{"title", "context", "links": [...], "issue", "body"}`。没有 `status`:删就是删,历史在 git;没有 id:id 就是 path。

### 用户层的 schema

写成 YAML 交给 `POST /api/collections/layers`,系统把它嵌进 `collections.json` 的 `layers[]`:

```yaml
layer: decision
format: markdown+frontmatter      # 或 json
title: title
fields:
  title:    {type: string, required: true}
  rejected: {type: "list[string]"}
  issue:    {type: ref, layer: issue}
```

类型:`string` `int` `bool` `"list[string]"` `ref` `"list[ref]"`。markdown 格式自动带 `body`。没有行为。

## manager.json

```json
{"work": "work_…"}
```

放在任何目录(含对象目录)下。解析:路径往上找最近的一个。变动投递到那个 work 的 `works/<work>/inbox.jsonl`:

```json
{"ts": "…", "layer": "issue", "path": "<对象 path>", "subject": "position …", "sha": "…", "by": "alice", "routed_by": "memory.talk"}
```

`routed_by` 是哪个目录的 `manager.json`('' = 根);work 层过来的是 `"parent"` 或那个 work 的 id。没人管 → `~/.memory.talk/unmanaged.jsonl`。
