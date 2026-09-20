# Collections(层、对象、仓库)

认知层的数据模型。机制见 [designs collections.md](../../designs/v5/metas/README.md);端点见 [api collections.md](../../api/v5/collections.md)。

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
| 形态 | 任何**不带后缀**的文件 | `<path>.issue/` 目录:`readme.md` + `positions/<主张>.md` | `<path>.card/readme.md` | 它的协议说了算 |
| id | 文件路径 | `path`(不含后缀) | `path` | `path` |
| 每个文件 | 原文 | frontmatter 字段 + markdown 正文 | frontmatter 字段 + markdown 正文 | 协议定 |
| 标题 | 文件名 | 目录名 | 目录名 | 目录名 |
| 层序 | 0(最底) | 1 | 2 | 之上,按 `collections.json` 的 `layers[]` 顺序 |

**层是一份 YAML 协议**(`memorytalk/backend/services/collections/layers/<层>.yaml`,用户层 `~/.memory.talk/layers/<名>.yaml`;写法见 [designs collections-layer.md](../../designs/v5/metas/layer.md)):对象目录名的正则和允许的位置、目录里每种文件的正则、每种文件的字段(类型 / 枚举 / 引用 / 必填)和正文。一次写 = 对这个目录的一批文件改动,引擎按协议校验,不过整批拒(422,理由带回)。读就是目录里的文件,不解析。对象目录里还可以放 `manager.json`(谁管它,机制文件,不在协议里)。目录树按主题组织,原文、`.issue/`、`.card/` 并排。

### issue 层(内置)

`<path>.issue/` 目录,两种文件;标题就是目录名。机制见 [designs issue.md](../../designs/v5/metas/issue.md)。

```
memory.talk/配置/该走文件还是环境变量.issue/
├── readme.md                          问题:字段 links / summary + 正文(问题的展开);必需,不能删
├── positions/
│   ├── 只用环境变量,不要配置文件.md     立场:文件名 = 主张;字段 links / rank / verdict + 正文(阐述 + ## 论证)
│   └── 走配置文件,环境变量只做覆盖.md
└── manager.json                       机制文件,可无
```

**readme.md**

```markdown
---
links:
- {type: specializes, target: memory.talk/配置/配置怎么管}
summary: 目前倾向只走环境变量
---

背景……
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `links[]` | list of `{type, target}` | `type` ∈ `specializes` / `suggested_by` / `questions` / `replaces` / `related`;`target` 是对端 issue 的 path(可带 `#<主张>`) |
| `summary` | text | 对整个问题现状的一句总结(manager 写) |

**positions/<主张>.md**

```markdown
---
rank: 1
verdict: 试过了,够用
links:
- {type: supports, target: memory.talk/配置/本地开发怎么给配置}
---

为什么这么主张……

## 论证

- 试了一遍,环境变量够用(work_try#9)
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `rank` | number | manager 的判定:数字越小越靠前;空 = 未判定。读的时候按 `rank` 升序再按文件名 |
| `verdict` | string | 为什么排这 |
| `links[]` | list of `{type, target}` | `type` ∈ `supports` / `refutes` / `depends_on` / `related` |

没有 `origin` / `card` 字段:issue 不记它从哪来、不记写成了哪张卡(卡记 issue)。没有 id:id 就是 path;立场没有 id:主张就是文件名。正文不锁:「不改旧论证、改主意加新立场」是约定,历史在 git。

### card 层(内置)

`<path>.card/readme.md`,一个文件;标题就是目录名。维基式事实条目:可改、可删,历史在 git;**没有分数、没有状态位**。机制见 [designs card.md](../../designs/v5/metas/card.md)。

```markdown
---
context: memory.talk v5
links: [memory.talk/配置/另一张卡]
issue: memory.talk/配置/该走文件还是环境变量
---

只用环境变量。配置文件是多出来的一份状态,要同步。
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `context` | string | 在哪成立:关于哪个项目 / 用户 / 场景。「本地论」在卡上的落法——不是治理字段,是事实陈述的一部分 |
| `links[]` | list of ref card | 相关卡的 path(内链,只有一种类型) |
| `issue` | ref issue | 讨论页:这张卡对应的 issue 的 path(卡记 issue,issue 不记卡) |

没有 `title`(目录名就是)、没有 `status`(删就是删)、没有 id(id 就是 path)。

### 用户层

`~/.memory.talk/layers/<名>.yaml`,一份和内置层一模一样的协议(文件名 = 层名);启动时载入,`collections.json` 的 `layers[]` 自动补一项 `{"name": "<名>", "builtin": false}`(一次最底层提交),新分支从始祖出发。协议写错(未知类型、正则不合法、`object.pattern` 不以 `.<名>` 结尾、两种文件重叠)或文件没了但 `collections.json` 里还有 → 启动报错。

## manager.json

```json
{"work": "work_…"}
```

放在任何目录(含对象目录)下。解析:路径往上找最近的一个。变动投递到那个 work 的 `works/<work>/inbox.jsonl`:

```json
{"ts": "…", "layer": "issue", "path": "<对象 path>", "subject": "position …", "sha": "…", "by": "alice", "routed_by": "memory.talk"}
```

`routed_by` 是哪个目录的 `manager.json`('' = 根);work 层过来的是 `"parent"` 或那个 work 的 id。没人管 → `~/.memory.talk/unmanaged.jsonl`。
