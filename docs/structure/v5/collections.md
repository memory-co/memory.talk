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

- **始祖** = 第一个提交,只有根上的 `collections.json`:`{"version": 1, "layers": [{"name": "origin", "builtin": true}, …, {"name": "experiment", "builtin": false}]}`,最底在前;只有名字和 `builtin`。所有分支从它出发;`git log collections.json` = 层的变化史。
- **一个动作一个提交**,信息以 `[层名]` 开头;跨层的决定是两个相邻提交 + 同一个 trailer。`git log --first-parent stack` 是全部认知的时间线;`git log layer/<层>` 是那一层的。
- **守卫**(写时,plumbing 内):① 后缀 / 机制规则说这个路径该归哪层,和声明的层不符 → 拒;② 路径已在别的层的树里 → 拒。所以 `[card]` 提交碰不到 `.issue/` 里的东西。
- **机制文件**:`collections.json` 归最底层;`manager.json` 归它所在目录按后缀规则算出的层。它们的变动不投递,也不出现在 tree / 目录里。
- 全部 plumbing(hash-object / update-index / write-tree / commit-tree / update-ref),不需要工作树、不装 hook——服务进程是唯一写者。

## 对象:带后缀的目录

| | origin | issue | card | 用户层 `<名>` |
|---|---|---|---|---|
| 形态 | 任何**不带后缀**的文件 | `<path>.issue/` 目录:`readme.md` + `meta.yaml` + `positions/*.md` | `<path>.card/` 目录:`readme.md` + `meta.yaml` | 它的 `check` 说了算 |
| id | 文件路径 | `path`(不含后缀) | `path` | `path` |
| 格式 | 原文 | markdown / yaml / markdown | markdown / yaml | 它的 `check` 说了算 |
| 标题 | 文件名 | 目录名 | 目录名 | 目录名 |
| 层序 | 0(最底) | 1 | 2 | 之上,按 `collections.json` 的 `layers[]` 顺序 |

**层就是一个校验函数 `check(diff, after)`**:一次写 = 对这个目录的一批文件改动,层看 diff(能表达只增不改、不能删)和改完的目录(跨文件约束),不过整批拒(422,理由带回)。读就是目录里的文件,不解析。对象目录里还可以放 `manager.json`(谁管它,机制文件,不在清单里)。目录树按主题组织,原文、`.issue/`、`.card/` 并排。

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

**check**:清单外的文件拒;`readme.md` 不能删;立场文件新建随意、改只能在末尾追加、不能删(改名 = 删 + 建,也不行);`meta.yaml` 按上表,`positions[].claim` 必须是已有立场,多余键拒。**读**:`files = {相对路径: 内容}`,不解析、不排序、不算分,怎么渲染是客户端的事。

没有 `origin` / `card` 字段:issue 不记它从哪来、不记写成了哪张卡(卡记 issue)。没有 id:id 就是 path;立场没有 id:主张就是文件名。

### card 层(内置)

`<path>.card/` 目录,两个文件;标题就是目录名。维基式事实条目:可改、可删,历史在 git;**没有分数、没有状态位**。机制见 [designs card.md](../../designs/v5/card.md)。

```
memory.talk/配置/配置只来自环境变量.card/
├── readme.md          正文;必需,不能删
├── meta.yaml          可无
└── manager.json       机制文件,可无
```

**meta.yaml**

```yaml
context: memory.talk v5
links: [memory.talk/配置/另一张卡]
issue: memory.talk/配置/该走文件还是环境变量
```

| 键 | 类型 | 说明 |
|---|---|---|
| `context` | string | 在哪成立:关于哪个项目 / 用户 / 场景。「本地论」在卡上的落法——不是治理字段,是事实陈述的一部分 |
| `links[]` | string[] | 相关卡的 path(内链,只有一种类型) |
| `issue` | string \| null | 讨论页:这张卡对应的 issue 的 path(卡记 issue,issue 不记卡) |

**check**:只能有这两个文件;`readme.md` 不能删;`meta.yaml` 多余的键拒。没有 `title`(目录名就是)、没有 `status`(删就是删)、没有 id(id 就是 path)。

### 用户层

`~/.memory.talk/layers/<名>.py`,里面一个 `Layer` 子类,和内置层一模一样(`name` / `files` / `check`);启动时载入,`collections.json` 的 `layers[]` 自动补一项 `{"name": "<名>", "builtin": false}`(一次最底层提交),新分支从始祖出发。文件没了但 `collections.json` 里还有 → 启动报错。写法见 [designs collections-layer.md](../../designs/v5/collections-layer.md)。

## manager.json

```json
{"work": "work_…"}
```

放在任何目录(含对象目录)下。解析:路径往上找最近的一个。变动投递到那个 work 的 `works/<work>/inbox.jsonl`:

```json
{"ts": "…", "layer": "issue", "path": "<对象 path>", "subject": "position …", "sha": "…", "by": "alice", "routed_by": "memory.talk"}
```

`routed_by` 是哪个目录的 `manager.json`('' = 根);work 层过来的是 `"parent"` 或那个 work 的 id。没人管 → `~/.memory.talk/unmanaged.jsonl`。
