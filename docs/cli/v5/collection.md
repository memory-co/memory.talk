# collection

认知层:层、树、对象 CRUD、历史、检索、行为、manager。对应 [`/api/collections`](../../api/v5/collections.md)。机制见 [`../../designs/v5/collections.md`](../../designs/v5/collections.md)。别名 `col`。

```
memory.talk collection
├── layers  [add <name> --schema <file>]
├── tree    [<path>]
├── ls      <layer> [--dir <路径>]
├── recall  [<layer>] [--dir <路径>]
├── search  <query> [--layer <层>]
│
├── read    <layer> <path> [--rev <sha>]
├── write   <layer> <path> (--field k=v ... | --data '<json>' | --content @file) [--reason '<…>']
├── edit    <layer> <path> (--field k=v ... | --data '<json>' | --content @file) [--reason '<…>']
├── rm      <layer> <path> [--reason '<…>']
├── log     <layer> <path>
│
├── act     <layer> <action> <path> --field k=v ... [--reason '<…>']
│
├── manager [<path>] [--set <work_id> | --unset]
└── managed [--work <work_id>]
```

每个写命令是 collections 仓库里的一个 `[层]` 提交,author = `--user`;`--reason` 进 commit body。碰了别的层的路径 → exit 1 `guard`。

## layers

```bash
memory.talk collection layers                          # 最底在前:origin / issue / card / 用户层;各自的 schema 与行为
memory.talk collection layers add decision --schema decision.yaml
```

schema 写法见 [`../../designs/v5/collections-layer.md`](../../designs/v5/collections-layer.md)(`list[…]` 要加引号)。

## tree / ls / recall / search

| 命令 | 说明 |
|---|---|
| `tree [<path>]` | 浏览目录:对象折成一项(带层名)、目录、origin 文件 |
| `ls <layer> [--dir]` | 一层的目录:按目录树列标题 |
| `recall [<layer>] [--dir]` | 目录渲染成文本(默认 card),给 agent 读 |
| `search <q> [--layer]` | `git grep`,每行一条:层 / 路径 / 行号 / 文本 |

## read

```bash
memory.talk collection read card memory.talk/配置/配置只来自环境变量
memory.talk collection read issue memory.talk/配置/该走文件还是环境变量        # 立场按 credence 排,附 up/down/neutral
memory.talk collection read origin memory.talk/配置/旧方案.md
memory.talk collection read card memory.talk/配置/配置只来自环境变量 --rev 527e8ae   # 历史版本
```

Markdown 输出:card 就是那份 markdown;issue 渲染成问题 + 立场列表;origin 原文。`--json` 是 API 的 Obj。

## write / edit / rm

```bash
# 字段:--field k=v(多次),或 --data '<json>';markdown 层的正文用 --field body=@正文.md
memory.talk collection write card memory.talk/配置/配置只来自环境变量 \
    --field title='配置只来自环境变量' --field context='memory.talk v5' --field body=@正文.md --reason '写 config.py 时定的'
memory.talk collection write issue memory.talk/配置/该走文件还是环境变量 --field question='配置该走文件还是环境变量?'
memory.talk collection write origin memory.talk/配置/旧方案.md --content @旧方案.md          # origin:原文
memory.talk collection edit  card memory.talk/配置/配置只来自环境变量 --field body=@新正文.md --reason '补理由'
memory.talk collection rm    card memory.talk/配置/配置只来自环境变量 --reason '过时'          # 删,历史在 git
```

`--field` 的值:字符串照写;列表用逗号(`--field links=a,b`);引用就是对端的 path。不合 schema → exit 1 `invalid`。已存在 → exit 1 `exists`。

## log

一个对象在它那层分支上的提交历史:sha / 谁 / 时间 / subject / Reason。

## act

行为(schema 之上的领域动作),payload 用 `--field`:

```bash
memory.talk collection act issue position <path> --field claim='只用环境变量'
memory.talk collection act issue argue    <path> --field position=p2 --field stance=1 --field comment='试过,够用' \
                                                 --field evidence.work_id=work_try --field evidence.rounds=9,10
memory.talk collection act issue link     <path> --field type=specializes --field target=<另一个 issue 的 path>
memory.talk collection act issue spawn    <path> --field position=p2 --field work_id=work_try
memory.talk collection act issue decide   <path> --field position=p2 --field card=<卡的 path> [--field context='…'] --reason '…'
memory.talk collection act card  discuss  <path> --field issue=<新 issue 的 path> --field question='要不要加?'
```

`--field a.b=v` 是嵌套(`evidence.work_id`);`stance` 收 `1` / `0` / `-1`。层没有这个行为 → exit 1 `no_action`。

## manager / managed

```bash
memory.talk collection manager memory.talk                 # 这个目录归谁管(最近的 manager.json)
memory.talk collection manager memory.talk --set work_…    # 在这个目录(或对象)下写 manager.json
memory.talk collection manager memory.talk --unset
memory.talk collection managed --work work_…               # 这个 work 管的所有对象
memory.talk collection managed                             # 没人管的对象
```
