# meta

认知层:层、树、最近、对象(目录里的文件)CRUD、历史。检索是顶层的 `memory.talk search`。对应 [`/api/metas`](../../api/v5/metas.md)。机制见 [`../../designs/v5/metas/README.md`](../../designs/v5/metas/README.md)。别名 `col`。

```
memory.talk meta
├── layers
├── tree    [<path>] [--layer <层>] [-r] [--candidate <名字>]
├── recent  [--layer <层>] [--path <目录>] [--limit 20] [--before <sha>]
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

每个写命令是 metas 仓库里的一个 `[层]` 提交,author = `--user`;`--subject` 是提交主题(不给就是 write / edit <path>),`--reason` 进 commit body。这批文件交给层的 check,不过 → exit 1 `invalid` 并打印理由;碰了别的层的路径 → exit 1 `guard`。

## layers

```bash
memory.talk meta layers                          # 最底在前:origin / issue / card / 用户层;各自的文件种类(* = 必需)
```

没有 `layers add`:加一层 = 往 `~/.memory.talk/layers/` 放一份 `<名>.yaml`(和内置层一模一样的协议),`server restart`。写法见 [`../../designs/v5/metas/layer.md`](../../designs/v5/metas/layer.md)。

## tree / recent

| 命令 | 说明 |
|---|---|
| `tree [<path>] [--layer] [-r] [--candidate]` | 浏览目录:对象折成一项(带层名)、目录、origin 文件;`--layer` 只看一层,`-r` 往下走到底拍平列出(`tree --layer card -r` = 全部卡片);末尾一行「可建:」列这里还能建什么;`--candidate` 问一个名字(对象目录名 / 文件路径)行不行 |
| `recent [--layer] [--path] [--limit] [--before]` | 最近改过的对象,每个一次、新的在前,每行 sha / 时间 / 谁 / 层 / 路径 / 动了哪些文件;最后一行给 `--before` 游标,再往下翻 |

## read

```bash
memory.talk meta read issue memory.talk/配置/该走文件还是环境变量        # 标题(目录名)+ 目录里每个文件
memory.talk meta read card  memory.talk/配置/配置只来自环境变量
memory.talk meta read origin memory.talk/配置/旧方案.md
memory.talk meta read card memory.talk/配置/配置只来自环境变量 --rev 527e8ae   # 历史版本
```

输出就是文件:`# <标题>` 之后每个文件一段 `== <相对路径>`;origin 是原文。`--json` 是 API 的 Obj(`files` 是 `{相对路径: 内容}`)。

## write / edit / rm

每个文件 = frontmatter 字段 + 正文;`--put <相对路径>=<内容>`(多次),内容可 `@file` / `@-`,edit 时 `null` 删。

```bash
memory.talk meta write issue memory.talk/配置/该走文件还是环境变量 --put readme.md=@问题.md --reason '撞见的'
memory.talk meta edit  issue memory.talk/配置/该走文件还是环境变量 \
    --put positions/只用环境变量.md=@立场.md --subject 'position …: 只用环境变量'       # 立场.md:frontmatter 里 rank / verdict / links,正文是阐述 + ## 论证
memory.talk meta edit  issue memory.talk/配置/该走文件还是环境变量 --put readme.md=@问题.md --subject 'summarize …'
memory.talk meta write card  memory.talk/配置/配置只来自环境变量 --put readme.md=@卡.md          # 卡.md 的 frontmatter 里写 context / links / issue
memory.talk meta write origin memory.talk/配置/旧方案.md --content @旧方案.md                   # origin:原文
memory.talk meta rm    card memory.talk/配置/配置只来自环境变量 --reason '过时'                   # 删,历史在 git
```

每个层有哪些文件、每种文件有哪些字段,看 `meta layers` 和 [`../../designs/v5/metas/layer.md`](../../designs/v5/metas/layer.md);想知道某个目录还能建什么,`meta tree <目录>`。不合协议 → exit 1 `invalid`,理由打印出来;已存在 → exit 1 `exists`。

## log

一个对象在它那层分支上的提交历史:sha / 谁 / 时间 / subject / Reason。

## manager / managed

```bash
memory.talk meta manager memory.talk                 # 这个目录归谁管(最近的 manager.json)
memory.talk meta manager memory.talk --set work_…    # 在这个目录(或对象)下写 manager.json
memory.talk meta manager memory.talk --unset
memory.talk meta managed --work work_…               # 这个 work 管的所有对象
memory.talk meta managed                             # 没人管的对象
```
