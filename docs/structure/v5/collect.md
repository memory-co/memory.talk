# Collect(层、对象、仓库)

认知层的数据模型。机制见 [designs collect.md](../../designs/v5/collect.md);端点见 [api collect.md](../../api/v5/collect.md)。

> 本篇取代原来的 [issue.md](issue.md) / [card.md](card.md) 里关于**存哪、id 形态、提交**的部分——issue 和 card 现在是 Collect 的两个 layer,对象模型(字段)不变,只是住的地方和 id 变了。

## 仓库:分层 git

```
~/.memory.talk/memory/           一个 git 仓库,自己实现的分层拓扑(语义对齐 collectbase,不依赖它)
  refs/heads/layer/origin        权威分支:只放这一层的文件,线性
  refs/heads/layer/issue
  refs/heads/layer/card
  refs/heads/layer/<用户层>      从始祖出发
  refs/heads/stack               合并视图:每次层提交后一个 merge 节点(parents = [stack, 层提交]),树 = 各层并集
  HEAD → stack;工作树跟着 stack(只为了人能 ls / cat,服务从不读它)
```

- **始祖** = 第一个提交,只有根上的 `layers` 文件(一行一层,最底在前)。所有分支从它出发。
- **一个动作一个提交**,信息以 `[层名]` 开头;跨层的决定是两个相邻提交 + 同一个 trailer。`git log --first-parent stack` 是全部认知的时间线;`git log layer/<层>` 是那一层的。
- **守卫**(写时,plumbing 内):① 后缀 / 机制规则说这个路径该归哪层,和声明的层不符 → 拒;② 路径已在别的层的树里 → 拒。所以 `[card]` 提交碰不到 `.issue/` 里的东西。
- **机制文件**:`layers`、`schemas/<层>.yaml` 归最底层;`manager.json` 归它所在目录按后缀规则算出的层。它们的变动不投递。
- 全部 plumbing(hash-object / update-index / write-tree / commit-tree / update-ref),不需要工作树、不装 hook——服务进程是唯一写者。

## 对象:带后缀的目录

| | origin | issue | card | 用户层 `<名>` |
|---|---|---|---|---|
| 形态 | 任何**不带后缀**的文件 | `<path>.issue/issue.json` | `<path>.card/card.md` | `<path>.<名>/<名>.md` 或 `.json` |
| id | 文件路径 | `path`(不含后缀) | `path` | `path` |
| 格式 | 原文 | JSON | markdown + frontmatter | schema 定 |
| 标题 | 文件名 | `question` | `title` | schema 的 `title` |
| 层序 | 0(最底) | 1 | 2 | 之上,按 `layers` 顺序 |

对象目录里还可以放 `manager.json`(谁管它)和附件。目录树按主题组织,原文、`.issue/`、`.card/` 并排。

### issue 的 body

```json
{"question": "…", "origin": {"task_id": "task_a", "rounds": [3], "origin": null},
 "card": "memory.talk/配置/配置只来自环境变量",
 "positions": [{"id": "p1", "claim": "…", "origin": null,
                "arguments": [{"id": "a1", "stance": 1, "comment": "", "evidence": {…}, "task_id": "task_try", "created_at": "…"}],
                "spawned_tasks": ["task_try"], "created_at": "…"}],
 "links": [{"type": "specializes", "target": "<issue path>"}],
 "created_at": "…"}
```

读视图每个立场附现算 `up / down / neutral / credence`,按 credence 倒序。**没有 `manager_task` 字段**——谁管它看目录下的 `manager.json`。`origin` / `evidence` 可以指 task 的 rounds,也可以指 origin 层的一个路径。

### card 的 body

```markdown
---
title: 配置只来自环境变量
context: memory.talk v5
links: memory.talk/配置/另一张卡
issue: memory.talk/配置/该走文件还是环境变量
---

正文
```

读出来是 `{"title", "context", "links": [...], "issue", "body"}`。**没有 status**:删就是删,历史在 git。

### 用户层的 schema

`schemas/<名>.yaml`,在仓库最底层:

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
{"task": "task_…"}
```

放在任何目录(含对象目录)下。解析:路径往上找最近的一个。变动投递到那个 task 的 `tasks/<task>/inbox.jsonl`:

```json
{"ts": "…", "layer": "issue", "path": "<对象 path>", "subject": "position …", "sha": "…", "by": "alice", "routed_by": "memory.talk"}
```

`routed_by` 是哪个目录的 `manager.json`('' = 根);task 层过来的是 `"parent"` 或那个 task 的 id。没人管 → `~/.memory.talk/unmanaged.jsonl`。
