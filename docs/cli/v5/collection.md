# collection

认知层:层、树、对象 CRUD、历史、检索、行为、manager。对应 [`/api/collections`](../../api/v5/collections.md)。机制见 [`../../designs/v5/collections.md`](../../designs/v5/collections.md)。别名 `col`。

```
memory.talk collection
├── layers  [add <name> --schema <file>]
├── tree    [<path>]
├── ls      <layer> [--dir <路径>]
├── search  <query> [--layer <层>]
│
├── read    <layer> <path> [--rev <sha>]
├── write   <layer> <path> (--put <文件>=<内容|@file|@-> ... | --field k=v ... | --data '<json>' | --content @file) [--reason '<…>']
├── edit    <layer> <path> (--put <文件>=<内容|@file|@-|null> ... | --field k=v ... | --data '<json>' | --content @file) [--reason '<…>']
├── rm      <layer> <path> [--reason '<…>']
├── log     <layer> <path>
│
├── act     <layer> <action> <path> (--field k=v ... | --data '<json>') [--reason '<…>']
│
├── manager [<path>] [--set <work_id> | --unset]
└── managed [--work <work_id>]
```

每个写命令是 collections 仓库里的一个 `[层]` 提交,author = `--user`;`--reason` 进 commit body。碰了别的层的路径 → exit 1 `guard`。

## layers

```bash
memory.talk collection layers                          # 最底在前:origin / issue / card / 用户层;各自允许的文件(格式,* 必需)与行为
memory.talk collection layers add decision --schema decision.yaml
```

schema 写法见 [`../../designs/v5/collections-layer.md`](../../designs/v5/collections-layer.md)(`list[…]` 要加引号)。

## tree / ls / search

| 命令 | 说明 |
|---|---|
| `tree [<path>]` | 浏览目录:对象折成一项(带层名)、目录、origin 文件 |
| `ls <layer> [--dir]` | 一层的目录:按目录树列标题 |
| `search <q> [--layer]` | `git grep`,每行一条:层 / 路径 / 行号 / 文本 |

## read

```bash
memory.talk collection read card memory.talk/配置/配置只来自环境变量
memory.talk collection read issue memory.talk/配置/该走文件还是环境变量        # 标题 = 目录名;立场按 meta.yaml 的排序,带 note 和论证
memory.talk collection read origin memory.talk/配置/旧方案.md
memory.talk collection read card memory.talk/配置/配置只来自环境变量 --rev 527e8ae   # 历史版本
```

Markdown 输出:card 就是那份 markdown;issue 渲染成标题 + 展开 + 总结 + 立场(序号、主张、note、阐述、论证);多文件用户层按文件分段;origin 原文。`--json` 是 API 的 Obj(含 `files`)。

## write / edit / rm

```bash
# 目录里的文件:--put <相对路径>=<内容>(多次);内容可 @file / @-;edit 时 null 删
memory.talk collection write issue memory.talk/配置/该走文件还是环境变量 --put readme.md=@背景.md --reason '撞见的'
memory.talk collection write issue memory.talk/配置/另一个问题                      # 什么都不给:一个空 readme.md
memory.talk collection edit  issue memory.talk/配置/该走文件还是环境变量 --put positions/乙.md=null --put meta.yaml=@meta.yaml
# 字段简写(只对单文件层:card、单文件用户层):--field k=v(多次),或 --data '<json>';正文用 --field body=@正文.md
memory.talk collection write card memory.talk/配置/配置只来自环境变量 \
    --field title='配置只来自环境变量' --field context='memory.talk v5' --field issue=memory.talk/配置/该走文件还是环境变量 --field body=@正文.md
memory.talk collection write origin memory.talk/配置/旧方案.md --content @旧方案.md          # origin:原文
memory.talk collection edit  card memory.talk/配置/配置只来自环境变量 --field body=@新正文.md --reason '补理由'
memory.talk collection rm    card memory.talk/配置/配置只来自环境变量 --reason '过时'          # 删,历史在 git
```

`--field` 的值:字符串照写;列表用逗号(`--field links=a,b`,所以含逗号的句子用 `--data`);引用就是对端的 path。整目录不合层的 schema → exit 1 `invalid`(清单外的文件、缺必填、多余字段)。已存在 → exit 1 `exists`。

## log

一个对象在它那层分支上的提交历史:sha / 谁 / 时间 / subject / Reason。

## act

行为(校验器之上的快捷方式),payload 用 `--field` 或 `--data '<json>'`:

```bash
memory.talk collection act issue position <path> --field claim='只用环境变量' --field body=@为什么.md
memory.talk collection act issue argue    <path> --data '{"claim": "只用环境变量", "comment": "试过,够用(work_try#9)"}'
memory.talk collection act issue link     <path> --field type=specializes --field target=<另一个 issue 的 path>
memory.talk collection act issue rank     <path> --data '{"positions": [{"claim": "只用环境变量", "note": "够用"}], "summary": "先这样"}'
memory.talk collection act card  discuss  <path> --field issue=<新 issue 的 path> --field readme='有人不同意'
```

`position` 新建 `positions/<claim>.md`,`argue` 往它的 `## 论证` 下加一行,`link` / `rank` 改 `meta.yaml`;谁、何时在 git。层没有这个行为 → exit 1 `no_action`。

## manager / managed

```bash
memory.talk collection manager memory.talk                 # 这个目录归谁管(最近的 manager.json)
memory.talk collection manager memory.talk --set work_…    # 在这个目录(或对象)下写 manager.json
memory.talk collection manager memory.talk --unset
memory.talk collection managed --work work_…               # 这个 work 管的所有对象
memory.talk collection managed                             # 没人管的对象
```
