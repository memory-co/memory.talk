# collections layer —— 一个层 = 一份 YAML 协议:路径 + 每种文件的 formatter(v5 设计)

> **状态:设计稿,代码未跟上。** 现在的层是一个 Python 类(`check` 写代码),前端对目录一无所知。本篇把层改成**一份 YAML**:声明这个层的对象目录里有哪些**路径**、每个路径的文件用什么 **formatter**(有哪些字段、字段是什么类型 / 枚举、正文是什么);后端用一个通用引擎把这份 YAML 同时当**校验规则**和**界面说明**;内置层和用户层是同一种东西。用户在前端的体感像 Notion 数据库里的一行:点开一个文件,上面是要填的字段(该选的给选项),下面写正文。总定位见 [README.md](README.md)。

相关:
- collections(层即分支,对象即带后缀的目录): [collections.md](collections.md)
- issue / card(两个内置层,本篇的示例就是它们的 YAML): [issue.md](issue.md) / [card.md](card.md)
- manager(`manager.json` 是机制文件,不在协议里): [manager.md](manager.md)

---

## 0. 为什么从 Python 换回 YAML

上一版让用户层写一个 `Layer` 子类,`check` 想多严就多严。代价是**规则只有代码能读**:前端拿不到目录长什么样,只能按 issue / card 各硬编码一个「只编辑 readme.md」的表单;用户层根本没有界面。于是出现「填个 a 就 201」——后端把关是对的,界面没把「这一层还有什么、哪些必填、哪些只能追加」露出来。

要让前后端联动,规则必须是**数据**而不是代码:一份 YAML,后端读它校验,前端读它画表单,两边看的是同一份,不会漂。代价是表达力有上限——协议里没有的规则就不能有。这是有意的:层是**协议**,不是程序;能用「路径 + 字段 + 枚举 + 引用 + 只追加」说清的规则才配叫层。

---

## 1. 一句话

**一个层 = 一份 YAML,说清两件事:**
1. **路径**:对象目录里允许哪些文件(固定名或带 `*` 的模式),哪些必需,哪些只能追加;
2. **formatter**:每个路径的文件长什么样——frontmatter 里有哪些字段(类型、枚举、引用、必填),正文是 markdown 还是没有正文。

其余一切(校验、表单、「这里能不能建」)由通用引擎从这份 YAML 推出来。

---

## 2. 协议

以 issue 为例,完整的一份(两种文件,都是「字段 + 正文」):

```yaml
layer: issue
description: 议事:一个问题、几个立场、每个立场下的论证;排序是 manager 的判定
files:
  - path: readme.md                 # 固定文件:问题本身
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
        ranking:                    # manager 的判定:排在前面的当前占优
          type: list
          item:
            type: object
            fields:
              position: {type: ref, file: "positions/*.md", required: true}   # 引用本目录里匹配这个模式的文件
              note:     {type: string}
        summary: {type: text}
      body: markdown                # 正文:问题的展开
    template: ""

  - path: positions/*.md            # 模式:* 是用户起的名字
    name: 主张                       # * 那一段叫什么,新建时问用户
    label: 立场
    append_only: true               # 已有的正文只能在末尾续写;字段可改;新建随意
    format:
      fields:
        links:
          type: list
          item:
            type: object
            fields:
              type:   {type: enum, values: [supports, refutes, depends_on, related], required: true}
              target: {type: ref, layer: issue, required: true}             # 对端 issue 的 path,可带 #<主张>
      body: markdown                # 正文:阐述 + ## 论证
    template: "\n\n## 论证\n"
```

**每个文件 = 字段 + 正文**,像 Notion 里的一行:上面是属性,下面是页面内容。没有单独的元数据文件——一个文件的元数据就在它自己头上(`.md` 的 frontmatter),字段和正文一起提交、一起有历史。

### 词汇表

**文件级**(`files[]` 每一项):

| 键 | 取值 | 含义 |
|---|---|---|
| `path` | 相对路径,可含一个 `*` | 目录里允许的文件。没有 `*` 是固定文件(至多一个);有 `*` 是一类文件(任意多个),`*` 不能含 `/` |
| `name` | 字符串 | 只对带 `*` 的路径:`*` 那一段叫什么(界面新建时问的问题) |
| `label` | 字符串 | 界面显示的名字 |
| `required` | bool | 建对象时必须有;之后不能删。只对固定文件 |
| `append_only` | bool | 已有文件的**正文**只能在末尾追加(字段照常可改);新建不限 |
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
| `ref` | `file: <本目录的路径模式>` | 关联(同一页里的行) | 下拉,选项 = 目录里匹配该模式的文件名 |
| `list` | `item: <字段>` | 多选 / 多个关联 | 可增删的列表 |
| `object` | `fields: {...}` | (一行里的一组子属性) | 一组子字段;只允许出现在 `list.item` 里,不再嵌套 |

每个字段都可以带 `required: true` 和 `description`。就这些;没有的类型不做,需要的层把字段留成 `text` 自己写。

**协议里没有的**:`manager.json`(机制文件,系统的);层序(在 `collections.json`);行为(没有行为);跨文件的算术或条件约束(只有 `ref {file}` 这一种跨文件关系)。

---

## 3. 引擎:一份 YAML 同时是规则和说明

后端只有**一个**校验器,读 YAML 执行,内置层和用户层走同一条路。它对每次写入(一批文件改动 + 改完的目录)做的事,全部能从协议逐条对应:

| 协议里的 | 引擎检查 |
|---|---|
| `files[].path` | 改动里每个路径必须匹配某一项;否则拒 |
| `required` | 改完的目录里必须有;删它拒 |
| `append_only` | 改前存在的文件,改后的**正文**必须是「改前正文 + 追加」;否则拒(frontmatter 不受限) |
| `format.fields` | 解析 frontmatter;未声明的键拒;`required` 的键要有;按 `type` 校验(枚举在 `values` 里、number 是数、date 能解析、list 是列表、object 递归) |
| `ref {file}` | 值必须是改完的目录里匹配该模式的文件名 |
| `ref {layer}` | 值是字符串路径;**不检查对端存在**(弱耦合,对端可能还没建、也可能删了) |

不在表里的就不校验。这就是「协议」的意思:后端不会比 YAML 更严,前端也不会比 YAML 更松。

---

## 4. 「这里能不能建」:后端直接回答

因为路径是协议的一部分,「在某个位置能建什么」是可以算出来的,不该让前端猜。一个只读端点:

```
GET /api/collections/affordances?path=<仓库里的一个目录或对象>
```

返回这个位置上**能创建的东西**,以及为什么不能:

```json
{"path": "memory.talk/配置",
 "objects": [{"layer": "issue"}, {"layer": "card"}, {"layer": "decision"}],         // 普通目录:能建任何层的对象、能放 origin 文件
 "files": []}

{"path": "memory.talk/配置/该走文件还是环境变量.issue",                              // 对象目录:能建这一层协议里的文件
 "objects": [],
 "files": [{"path": "readme.md", "label": "问题", "exists": true, "can": false, "reason": "固定文件,已存在"},
           {"path": "positions/*.md", "name": "主张", "label": "立场", "exists": false, "can": true, "existing": ["只用环境变量"]}]}
```

前端的「新建」按钮只从这个接口的 `can: true` 里长出来;树浏览到任何位置,该位置能干什么一目了然。内容合不合规仍然由写入时的校验说了算(以及 §5 的 dry-run)。

---

## 5. API

| 端点 | 变化 |
|---|---|
| `GET /api/collections/layers` | 每层带整份协议(YAML 转 JSON),前端据此画表单 |
| `GET /api/collections/affordances?path=` | 新增,§4 |
| `POST` / `PUT /api/collections/{layer}/{path}?dry_run=1` | 走完校验不提交,返回 `{"ok": true}` 或 `{"ok": false, "reason": "…"}`(200) |
| 写入口 | 不变:`files` 一批文件改动,`subject` / `reason` 可选 |

---

## 6. 前端:像 Notion 的一行

前端不再认识「issue」「card」,只认识协议:

- **层 = 一个数据库**,对象列表就是它的行。
- **对象 = 一页**,页里按协议的 `files` 顺序列出文件:固定文件一项,带 `*` 的一组(每个已有文件一项,末尾一个「新建 <label>」按钮,点了问「<name>」)。
- **文件 = 打开就是「属性 + 正文」**:上面是 `fields` 的表单(该选的下拉、该关联的搜索、`ref {file}` 从本页的文件里选),下面是 `body` 的编辑器;没有 `fields` 就只有正文;`append_only` 的文件旧正文只读、下面一个追加框,字段照常可改。
- **建对象** = 建它所有 `required` 的文件,各自按 `template` 预填。
- **保存前 dry-run**,不过的理由显示在对应文件旁边,保存按钮禁用;通过了再真提交。
- 读的一侧允许按层做只读渲染(issue 的立场按 `ranking` 排、卡片 `context` 放标题下),规则:**特化只产生展示,不产生写入**。

---

## 7. 内置层也是 YAML

`memorytalk/backend/services/collections/layers/` 下放 `origin.yaml` `issue.yaml` `card.yaml`;用户层放 `~/.memory.talk/layers/<名>.yaml`,启动时一起载入,登记进 `collections.json`(只记名字和 `builtin`)。**没有 Python 子类这条路了**——协议说不清的规则就不该是层的规则。

**origin** 是唯一的特例:没有目录、没有协议,`origin.yaml` 只有 `layer: origin` 和一句 `description`,引擎对它永远放行。

**card**:一个文件,字段 + 正文。

```yaml
layer: card
description: 记事:一条事实,像维基词条;标题是目录名
files:
  - path: readme.md
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

- 载入时校验 YAML 合不合协议词汇表(未知的键、未知的 `type`、`object` 嵌套过深、`*` 含 `/`),不合的层启动即报错。
- 测试:每个载入的层,按 `required` + `template` 建出来的目录必须过校验;带 `*` 的路径用 `name` 造一个文件也必须过;`append_only` 的文件改正文必须被拒。内置层和 `<home>/layers/*.yaml` 一起跑。

---

## 9. 有意不定的事

- **`ref {layer}` 要不要可选地检查对端存在**:先不,弱耦合;要的话加 `exists: true`。
- **`append_only` 的粒度**:现在是「末尾续写任意文本」;要不要限定成「只能加一个列表项」,等 issue 用起来再定。
- **标题**:一律目录名;要不要允许某个字段当标题,先不。
- **协议版本**:YAML 里加不加 `version: 1`,等第一次要改词汇表时再加。
