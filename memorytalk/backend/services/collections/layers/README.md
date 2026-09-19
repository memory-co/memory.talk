# layers —— 一个层 = 一份 YAML 协议

一份 YAML 说清三件事:**对象目录**叫什么(正则,必须以 `.<层>` 结尾)、能放哪(`under`);目录里允许哪些**文件**(每种一个正则);每种文件的 **formatter**(frontmatter 字段 + 正文)。
`protocol.py` 是唯一的引擎:读这份 YAML 校验写入,也把它原样交给 `GET /api/collections/layers` 让前端画表单。**没有 Python 层**:协议说不清的规则就不是层的规则。协议全文见 [docs/designs/v5/collections-layer.md](../../../../../docs/designs/v5/collections-layer.md)。

```yaml
layer: issue
object: {pattern: ^(?P<name>[^/]+)\.issue$, name: 问题, under: .*}
files:
  - pattern: ^readme\.md$                   # 固定文件:没有捕获组,至多一个
    label: 问题
    required: true                            # 建对象时必须有;之后不能删
    format:
      fields:                                 # frontmatter;类型 string / text / number / bool / date / enum / ref / list / object
        links: {type: list, item: {type: object, fields: {type: {type: enum, values: [...], required: true}, target: {type: ref, layer: issue, required: true}}}}
      body: markdown                          # 正文:markdown | text
    template: ""
  - pattern: ^positions/(?P<name>[^/]+)\.md$  # 一类文件:命名组 name 由用户起
    name: 主张
    label: 立场
    format: {fields: {rank: {type: number}, verdict: {type: string}, links: {...}}, body: markdown}
    template: "\n\n## 论证\n"
```

## 引擎做什么(`Layer.check(changes, after)`)

| 协议里的 | 检查 |
|---|---|
| `object.pattern` / `under` | 新建对象:目录名整段匹配、父目录匹配 `under`、不在别的对象目录里 |
| `files[].pattern` | 改动里每个路径必须整段匹配某一种;固定文件至多一个 |
| `required` | 改完的目录里必须有;删它拒 |
| `format.fields` | 解 frontmatter(必须是键值表);未声明的键拒;`required` 的键要有;按类型校验(enum 在 values 里、number、date、list、object 递归) |
| 没有 `fields` | 文件不能有 frontmatter |

没有跨文件约束:每个文件只按自己的 formatter 校验,文件之间只有路径规则。载入时校验协议本身(未知键 / 类型、正则不合法、捕获组不叫 `name`、`object.pattern` 不以 `\.<层>$` 结尾、两种文件重叠),不合的层启动即报错。

## 给前端的

- `GET /api/collections/layers`:每层 `protocol` = 这份 YAML 的 JSON,每种文件多算好 `fixed` / `example`(`positions/{name}.md`)。
- `GET /api/collections/tree?path=&candidate=`:`can_create` 说这个目录还能建什么(普通目录按各层 `object` 规则,对象目录按文件种类),`candidate` 回答一个名字行不行。
- `POST` / `PUT …?dry_run=1`:只校验不提交,返回 `{ok, reason}`。

## 内置层与用户层

内置 `origin.yaml` `issue.yaml` `card.yaml` 在本目录,顺序 `BUILTIN_ORDER`(最底在前);origin 没有对象目录、不校验。用户层 `~/.memory.talk/layers/<名>.yaml`,文件名 = 层名,启动时一起载入、登记进 `collections.json`(只记名字和 `builtin`)。加一层 = 放一份 YAML,重启。
