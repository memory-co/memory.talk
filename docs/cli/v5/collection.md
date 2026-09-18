# collection

认知层:层、树、对象(目录里的文件)CRUD、历史、检索。对应 [`/api/collections`](../../api/v5/collections.md)。机制见 [`../../designs/v5/collections.md`](../../designs/v5/collections.md)。别名 `col`。

```
memory.talk collection
├── layers
├── tree    [<path>] [--candidate <名字>]
├── ls      <layer> [--dir <路径>]
├── search  <query> [--layer <层>]
│
├── read    <layer> <path> [--rev <sha>]
├── write   <layer> <path> (--put <文件>=<内容|@file|@-> ... | --content @file) [--subject '<…>'] [--reason '<…>']
├── edit    <layer> <path> (--put <文件>=<内容|@file|@-|null> ... | --content @file) [--subject '<…>'] [--reason '<…>']
├── rm      <layer> <path> [--reason '<…>']
├── log     <layer> <path>
│
├── manager [<path>] [--set <work_id> | --unset]
└── managed [--work <work_id>]
```

每个写命令是 collections 仓库里的一个 `[层]` 提交,author = `--user`;`--subject` 是提交主题(不给就是 write / edit <path>),`--reason` 进 commit body。这批文件交给层的 check,不过 → exit 1 `invalid` 并打印理由;碰了别的层的路径 → exit 1 `guard`。

## layers

```bash
memory.talk collection layers                          # 最底在前:origin / issue / card / 用户层;各自的文件种类(* = 必需)
```

没有 `layers add`:加一层 = 往 `~/.memory.talk/layers/` 放一份 `<名>.yaml`(和内置层一模一样的协议),`server restart`。写法见 [`../../designs/v5/collections-layer.md`](../../designs/v5/collections-layer.md)。

## tree / ls / search

| 命令 | 说明 |
|---|---|
| `tree [<path>] [--candidate]` | 浏览目录:对象折成一项(带层名)、目录、origin 文件;末尾一行「可建:」列这里还能建什么;`--candidate` 问一个名字(对象目录名 / 文件路径)行不行 |
| `ls <layer> [--dir]` | 一层的目录:按目录树列标题 |
| `search <q> [--layer]` | `git grep`,每行一条:层 / 路径 / 行号 / 文本 |

## read

```bash
memory.talk collection read issue memory.talk/配置/该走文件还是环境变量        # 标题(目录名)+ 目录里每个文件
memory.talk collection read card  memory.talk/配置/配置只来自环境变量
memory.talk collection read origin memory.talk/配置/旧方案.md
memory.talk collection read card memory.talk/配置/配置只来自环境变量 --rev 527e8ae   # 历史版本
```

输出就是文件:`# <标题>` 之后每个文件一段 `== <相对路径>`;origin 是原文。`--json` 是 API 的 Obj(`files` 是 `{相对路径: 内容}`)。

## write / edit / rm

每个文件 = frontmatter 字段 + 正文;`--put <相对路径>=<内容>`(多次),内容可 `@file` / `@-`,edit 时 `null` 删。

```bash
memory.talk collection write issue memory.talk/配置/该走文件还是环境变量 --put readme.md=@问题.md --reason '撞见的'
memory.talk collection edit  issue memory.talk/配置/该走文件还是环境变量 \
    --put positions/只用环境变量.md=@立场.md --subject 'position …: 只用环境变量'       # 立场.md:frontmatter 里 rank / verdict / links,正文是阐述 + ## 论证
memory.talk collection edit  issue memory.talk/配置/该走文件还是环境变量 --put readme.md=@问题.md --subject 'summarize …'
memory.talk collection write card  memory.talk/配置/配置只来自环境变量 --put readme.md=@卡.md          # 卡.md 的 frontmatter 里写 context / links / issue
memory.talk collection write origin memory.talk/配置/旧方案.md --content @旧方案.md                   # origin:原文
memory.talk collection rm    card memory.talk/配置/配置只来自环境变量 --reason '过时'                   # 删,历史在 git
```

每个层有哪些文件、每种文件有哪些字段,看 `collection layers` 和 [`../../designs/v5/collections-layer.md`](../../designs/v5/collections-layer.md);想知道某个目录还能建什么,`collection tree <目录>`。不合协议 → exit 1 `invalid`,理由打印出来;已存在 → exit 1 `exists`。

## log

一个对象在它那层分支上的提交历史:sha / 谁 / 时间 / subject / Reason。

## manager / managed

```bash
memory.talk collection manager memory.talk                 # 这个目录归谁管(最近的 manager.json)
memory.talk collection manager memory.talk --set work_…    # 在这个目录(或对象)下写 manager.json
memory.talk collection manager memory.talk --unset
memory.talk collection managed --work work_…               # 这个 work 管的所有对象
memory.talk collection managed                             # 没人管的对象
```
