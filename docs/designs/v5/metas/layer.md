# metas layer —— 一个层 = 一份 YAML 协议:路径 + 每种文件的 formatter(v5 设计)

> **状态:已实施。** 层 = 一份 YAML(`memorytalk/backend/services/metas/layers/<层>.yaml`,用户层 `~/.memory.talk/layers/<名>.yaml`),`protocol.py` 是唯一引擎:读它校验写入,也原样交给 `GET /api/metas/layers`;`GET /tree` 带 `can_create` / `candidate`,`POST` / `PUT` 带 `dry_run`;前端的对象编辑器完全由协议驱动。总定位见 [README.md](../README.md)。

相关:
- metas(层即分支,对象即带后缀的目录): [README.md](README.md)
- issue / card(两个内置层,本篇的示例就是它们的 YAML): [issue.md](issue.md) / [card.md](card.md)
- manager(`manager.json` 是机制文件,不在协议里): [manager.md](manager.md)

---

## 0. 为什么从 Python 换回 YAML

上一版让用户层写一个 `Layer` 子类,`check` 想多严就多严。代价是**规则只有代码能读**:前端拿不到目录长什么样,只能按 issue / card 各硬编码一个「只编辑 readme.md」的表单;用户层根本没有界面。于是出现「填个 a 就 201」——后端把关是对的,界面没把「这一层还有什么、哪些必填、哪些只能追加」露出来。

要让前后端联动,规则必须是**数据**而不是代码:一份 YAML,后端读它校验,前端读它画表单,两边看的是同一份,不会漂。代价是表达力有上限——协议里没有的规则就不能有。这是有意的:层是**协议**,不是程序;能用「路径 + 字段 + 枚举 + 引用」说清的规则才配叫层。

---

## 1. 一句话

**一个层 = 一份 YAML,说清三件事:**
1. **对象目录**:这一层的对象目录叫什么样的名字(正则,必须以 `.<层>` 结尾)、允许放在哪些位置;
2. **路径**:对象目录里允许哪些文件——每种文件一个**正则**,匹配的路径才能进来;哪些必需;
3. **formatter**:每个路径的文件长什么样——frontmatter 里有哪些字段(类型、枚举、引用、必填),正文是 markdown 还是没有正文。

其余一切(校验、表单、tree 里的「这里能不能建」)由通用引擎从这份 YAML 推出来。

---

## 2. 协议

以 issue 为例,完整的一份(两种文件,都是「字段 + 正文」):

```yaml
layer: issue
description: 议事:一个问题、几个立场、每个立场下的论证;排序是 manager 的判定
object:
  pattern: ^(?P<name>[^/]+)\.issue$   # 对象目录的名字;捕获组 name 就是标题;必须以 .issue 结尾(层守卫靠后缀认归属)
  name: 问题                         # name 那段叫什么,新建对象时问用户
  under: .*                          # 允许放在哪些目录下(相对仓库根的目录路径的正则);默认任意
files:
  - pattern: ^readme\.md$           # 正则,匹配对象目录内的相对路径;没有捕获组 = 固定文件,至多一个
    label: 问题
    required: true                  # 建对象时必须有;之后不能删
    format:
      fields:                       # frontmatter
        links:
          type: list
          item:
            type: object
            fields:
              type:   {type: enum, values: [specializes, suggested_by, questions, replaces, related], required: true}
              target: {type: ref, layer: issue, required: true}
      body: markdown                # 正文:问题的展开
    template: ""

  - pattern: ^positions/(?P<name>[^/]+)\.md$   # 带命名捕获组 name = 一类文件,任意多个;name 那段由用户起
    name: 主张                       # 捕获组 name 叫什么,新建时问用户
    label: 立场
    format:
      fields:
        links:
          type: list
          item:
            type: object
            fields:
              type:   {type: enum, values: [supports, refutes, depends_on, related], required: true}
              target: {type: ref, layer: issue, required: true}             # 对端 issue 的 path,可带 #<主张>
        rank:    {type: number, description: manager 的判定:数字越小越靠前;空 = 未判定}
        verdict: {type: string, description: 为什么排这}
      body: markdown                # 正文:阐述 + ## 论证
    template: "\n\n## 论证\n"
```

**每个文件 = 字段 + 正文**,像 Notion 里的一行:上面是属性,下面是页面内容。没有单独的元数据文件——一个文件的元数据就在它自己头上(`.md` 的 frontmatter),字段和正文一起提交、一起有历史。

### 词汇表

**对象级**(`object`):

| 键 | 取值 | 含义 |
|---|---|---|
| `pattern` | 正则,整段匹配对象目录名(不含父路径) | 必须带命名捕获组 `name`,且以 `\.<层>$` 结尾——后缀是层归属的依据,不能变。省略 = `^(?P<name>[^/]+)\.<层>$` |
| `name` | 字符串 | `name` 那段叫什么(新建对象时问的问题;它就是标题) |
| `under` | 正则,整段匹配父目录路径(相对仓库根,`''` 是根) | 这一层的对象允许放在哪。省略 = 任意目录;不能放进别的对象目录里(对象不嵌套,这条是系统规则) |

**文件级**(`files[]` 每一项):

| 键 | 取值 | 含义 |
|---|---|---|
| `pattern` | 正则,整段匹配对象目录内的相对路径 | 目录里允许的文件。**没有捕获组** = 固定文件(至多一个);**有命名捕获组 `name`** = 一类文件(任意多个),`name` 那段由用户起,系统把它代回正则得到文件名。一个路径最多匹配一种文件,载入时检查各 `pattern` 两两不相交(用固定样例试) |
| `name` | 字符串 | 只对带捕获组的 `pattern`:那一段叫什么(界面新建时问的问题) |
| `label` | 字符串 | 界面显示的名字 |
| `required` | bool | 建对象时必须有;之后不能删。只对固定文件 |
| `format.fields` | 字段表 | 文件头部的字段(`.md` 的 frontmatter)。没有 `fields` 就是纯正文文件 |
| `format.body` | `markdown` / `text` | 字段之后的正文 |
| `template` | 字符串 | 新建时正文的初始内容 |

**字段级**(`fields` 里每一项,Notion 的「属性类型」):

| `type` | 附加键 | Notion 里对应 | 前端控件 |
|---|---|---|---|
| `string` | | 文本 | 单行输入 |
| `text` | | 文本(多行) | 多行输入 |
| `number` | | 数字 | 数字输入 |
| `bool` | | 复选 | 开关 |
| `date` | | 日期 | 日期选择 |
| `enum` | `values: [...]` | 选择 | 下拉 |
| `ref` | `layer: <层>` | 关联(另一个库) | 搜索选一个对象的 path |
| `list` | `item: <字段>` | 多选 / 多个关联 | 可增删的列表 |
| `object` | `fields: {...}` | (一行里的一组子属性) | 一组子字段;只允许出现在 `list.item` 里,不再嵌套 |

每个字段都可以带 `required: true` 和 `description`。就这些;没有的类型不做,需要的层把字段留成 `text` 自己写。

**协议里没有的**:`manager.json`(机制文件,系统的);层序(在 `metas.json`);行为(没有行为);**任何跨文件的约束**——每个文件只按自己的 formatter 校验,文件之间只有路径规则。

---

## 3. 引擎:一份 YAML 同时是规则和说明

后端只有**一个**校验器,读 YAML 执行,内置层和用户层走同一条路。它对每次写入(一批文件改动 + 改完的目录)做的事,全部能从协议逐条对应:

| 协议里的 | 引擎检查 |
|---|---|
| `object.pattern` / `object.under` | 新建对象时,目录名必须整段匹配 `pattern`,父目录必须匹配 `under`,且父目录不在任何对象目录之内;否则拒 |
| `files[].pattern` | 改动里每个路径必须整段匹配某一项的正则;否则拒。固定文件(无捕获组)至多一个 |
| `required` | 改完的目录里必须有;删它拒 |
| `format.fields` | 解析 frontmatter;未声明的键拒;`required` 的键要有;按 `type` 校验(枚举在 `values` 里、number 是数、date 能解析、list 是列表、object 递归) |
| `ref {layer}` | 值是字符串路径;**不检查对端存在**(弱耦合,对端可能还没建、也可能删了) |

不在表里的就不校验。这就是「协议」的意思:后端不会比 YAML 更严,前端也不会比 YAML 更松。

---

## 4. 「这里能不能建」:tree 接口顺带回答

因为每种文件、每个对象目录都有正则,「某个目录下还能加什么」是可以算出来的,不该让前端猜。也不用新接口——浏览目录本来就走 `GET /api/metas/tree?path=`,它现在只返回「这里有什么」(`items`);多加一个字段 **`can_create`**,说「这里还能建什么」:

```json
GET /api/metas/tree?path=memory.talk/配置                 // 普通目录
{"path": "memory.talk/配置",
 "items": [ …现在的 dir / file / object 列表… ],
 "can_create": {
   "objects": [                                                // 按每一层的 object 规则:能不能在这建对象
     {"layer": "issue",    "pattern": "^(?P<name>[^/]+)\\.issue$",    "name": "问题", "can": true,  "example": "<问题>.issue"},
     {"layer": "card",     "pattern": "^(?P<name>[^/]+)\\.card$",     "name": "标题", "can": true,  "example": "<标题>.card"},
     {"layer": "decision", "pattern": "^(?P<name>[^/]+)\\.decision$", "name": "决定", "can": false, "reason": "decision 只允许放在 decisions/ 下(under)"}],
   "files": [{"layer": "origin", "can": true}]}}              // origin 文件总能放

GET /api/metas/tree?path=memory.talk/配置/该走文件还是环境变量.issue   // 对象目录:按这一层协议逐种文件回答
{"path": "…/该走文件还是环境变量.issue",
 "layer": "issue",
 "items": [ …readme.md、positions/ … ],
 "can_create": {
   "objects": [],                                              // 对象不嵌套
   "files": [
     {"pattern": "^readme\\.md$", "label": "问题", "fixed": true, "existing": ["readme.md"], "can": false, "reason": "固定文件,已存在"},
     {"pattern": "^positions/(?P<name>[^/]+)\\.md$", "label": "立场", "name": "主张", "fixed": false,
      "existing": ["positions/只用环境变量.md"], "can": true, "example": "positions/<主张>.md"}]}}

GET /api/metas/tree?path=….issue/positions                 // 对象里的子目录:只列正则能落到这里的那些文件种类
{"path": "…/positions", "layer": "issue", "items": [ … ],
 "can_create": {"objects": [], "files": [{"pattern": "^positions/(?P<name>[^/]+)\\.md$", "label": "立场", "name": "主张", "fixed": false, "existing": ["positions/只用环境变量.md"], "can": true}]}}
```

再加一个可选参数 **`candidate`**,问「这个名字行不行」——在普通目录问的是对象目录名,在对象目录问的是文件路径;有它时多返回一个 `candidate` 字段:

```json
GET /api/metas/tree?path=memory.talk/配置&candidate=要不要加配置文件.issue
"candidate": {"name": "要不要加配置文件.issue", "matches": {"layer": "issue", "name": "要不要加配置文件"}, "exists": false, "can": true}

GET /api/metas/tree?path=….issue&candidate=positions/走配置文件.md
"candidate": {"name": "positions/走配置文件.md", "matches": {"pattern": "^positions/(?P<name>[^/]+)\\.md$", "label": "立场"}, "exists": false, "can": true}

GET /api/metas/tree?path=….issue&candidate=notes.txt
"candidate": {"name": "notes.txt", "matches": null, "can": false, "reason": "不匹配 issue 的任何一种文件"}
```

前端的「新建」按钮只从 `can_create` 里 `can: true` 的项长出来,用户填的名字在提交前先用 `candidate` 问一遍;浏览到任何位置,该位置有什么、能建什么,一次请求都在。内容合不合规仍然由写入时的校验说了算(以及 §5 的 dry-run)。

---

## 5. API

| 端点 | 变化 |
|---|---|
| `GET /api/metas/layers` | 每层带整份协议(YAML 转 JSON),前端据此画表单 |
| `GET /api/metas/tree?path=[&candidate=]` | 返回体多一个 `can_create`(这里能建什么),带 `candidate` 时多一个 `candidate`(这个名字行不行),§4 |
| `POST` / `PUT /api/metas/{layer}/{path}?dry_run=1` | 走完校验不提交,返回 `{"ok": true}` 或 `{"ok": false, "reason": "…"}`(200) |
| 写入口 | 不变:`files` 一批文件改动,`subject` / `reason` 可选 |

---

## 6. 前端:像 Notion 的一行

前端不再认识「issue」「card」,只认识协议:

- **层 = 一个数据库**,对象列表就是它的行。
- **对象 = 一页**,页里按协议的 `files` 顺序列出文件:固定文件一项,带捕获组的一组(每个已有文件一项,末尾一个「新建 <label>」按钮,点了问「<name>」,名字代回正则得到路径,先拿 `candidate` 问后端再建)。
- **文件 = 打开就是「属性 + 正文」**:上面是 `fields` 的表单(该选的下拉、该关联的搜索),下面是 `body` 的编辑器;没有 `fields` 就只有正文。
- **建对象** = 在某个目录里点「新建 <层>」,问一个「<object.name>」,名字代回 `object.pattern` 得到目录名;然后建它所有 `required` 的文件,各自按 `template` 预填。
- **保存前 dry-run**,不过的理由显示在对应文件旁边,保存按钮禁用;通过了再真提交。
- 读的一侧允许按层做只读渲染(issue 的立场按各自的 `rank` 排、卡片 `context` 放标题下),规则:**特化只产生展示,不产生写入**。

---

## 7. 内置层也是 YAML

`memorytalk/backend/services/metas/layers/` 下放 `origin.yaml` `issue.yaml` `card.yaml`;用户层放 `~/.memory.talk/layers/<名>.yaml`,启动时一起载入,登记进 `metas.json`(只记名字和 `builtin`)。**没有 Python 子类这条路了**——协议说不清的规则就不该是层的规则。

**origin** 是唯一的特例:没有对象目录、没有协议,`origin.yaml` 只有 `layer: origin` 和一句 `description`;任何不带层后缀的文件都是它,引擎对它永远放行。

**card**:一个文件,字段 + 正文。

```yaml
layer: card
description: 记事:一条事实,像维基词条;标题是目录名
object:
  name: 标题                          # pattern 省略 = ^(?P<name>[^/]+)\.card$
files:
  - pattern: ^readme\.md$
    label: 卡片
    required: true
    format:
      fields:
        context: {type: string, description: 在哪成立}
        links:   {type: list, item: {type: ref, layer: card}}
        issue:   {type: ref, layer: issue, description: 讨论页}
      body: markdown
```

**issue**:§2 那份。

---

## 8. 漂移

不存在了——规则只有一份。要防的只剩「协议本身写错」:

- 载入时校验 YAML 合不合协议词汇表(未知的键、未知的 `type`、`object` 字段嵌套过深、正则编译不过、捕获组不叫 `name`、`object.pattern` 不以 `\.<层>$` 结尾、两种文件的正则能匹配同一个路径),不合的层启动即报错。
- 测试:每个载入的层,按 `required` + `template` 建出来的目录必须过校验;带捕获组的正则用一个样例名代回去造一个文件也必须过。内置层和 `<home>/layers/*.yaml` 一起跑。

---

## 9. 有意不定的事

- **`ref {layer}` 要不要可选地检查对端存在**:先不,弱耦合;要的话加 `exists: true`。
- **标题**:一律目录名;要不要允许某个字段当标题,先不。
- **协议版本**:YAML 里加不加 `version: 1`,等第一次要改词汇表时再加。
