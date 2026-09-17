# collections layer —— 一个层 = 一个 check + 一个 schema(v5 设计)

> **状态:设计稿,代码未跟上。** 现在的层只有 `check(diff, after)`,后端知道目录里能放什么、哪些只能追加,前端一无所知,只能按 issue / card 各硬编码一个「只编辑 readme.md」的表单。本篇给层加第二个方法 **`schema()`**:把目录的形状说给前端听,前端据此对任何层生成建 / 改表单;`check` 仍是唯一的裁判。总定位见 [README.md](README.md)。

相关:
- collections(层即分支,对象即带后缀的目录): [collections.md](collections.md)
- issue / card(两个内置层,本篇的 schema 示例就是它们): [issue.md](issue.md) / [card.md](card.md)
- manager(任何层的任何目录都可以放 `manager.json`,不在 schema 里): [manager.md](manager.md)

---

## 0. 为什么要有 schema

写入这一侧已经对了:一次写 = 对对象目录的一批文件改动,层的 `check` 看 diff 决定过不过,规则再细都行。问题在**读这一侧的另一半**——界面。界面要建一个 issue,得知道:目录里能有哪些文件、哪个必须有、哪个是 yaml 要填哪些键、哪个只能追加、带 `*` 的路径让用户起什么名。这些信息现在只存在于 `check` 的 if 语句里,前端拿不到,只好自己猜一份。两份规则各写一遍,必然脱节:后端允许加立场,界面没入口;界面填个 `a` 就 201,用户以为没校验。

所以层要说两种话:对**写入**说「过不过」(`check`),对**界面**说「长什么样」(`schema`)。两者写在同一个类里,漂了一眼能看见,还能用测试钉住:按 schema 的模板建出来的目录必须过 check。

---

## 1. 接口:两个方法

```python
class Layer(ABC):
    name: str
    def check(self, changes: list[Change], after: dict[str, bytes]) -> str | None: ...   # 裁判:这批改动过不过
    def schema(self) -> Schema: ...                                                     # 说明书:目录长什么样,给界面出表单
```

分工要严格:

| | `check` | `schema` |
|---|---|---|
| 谁用 | 服务写入口,每次 put 都过 | `GET /api/collections/layers`,前端读 |
| 说什么 | 过 / 不过 + 理由 | 有哪些文件、每个文件什么格式、必不必需、能不能改、yaml 有哪些键、新建用什么模板 |
| 能多细 | 任意(代码) | 固定词汇表(§2),前端只认这几种 |
| 谁是权威 | **它** | 它只是 check 的一份「可读投影」,写不进去的还是写不进去 |

`schema` 不是校验规则的完整表达——「`meta.positions[].claim` 必须是已有立场」这种跨文件约束只在 `check` 里;schema 只需要说到「这个键是引用,指向本目录 `positions/*.md` 的文件名」,前端据此做成下拉,真正的把关还是 check。前端**永远**不用 schema 判断合法性,只用它决定画什么控件。

---

## 2. schema 的形状

```yaml
layer: issue
title: dirname                     # 标题来源,目前只有这一种
files:                             # 目录清单,顺序就是表单顺序
  - pattern: readme.md
    format: markdown               # markdown | yaml | text
    required: true                 # 建对象时必须有;改时不能删
    edit: full                     # full | append | none
    label: 问题的展开
    template: ""                   # 新建时的初始内容
  - pattern: meta.yaml
    format: yaml
    required: false
    edit: full
    label: 边与排序
    fields:                        # yaml 的键:有它,前端出字段表单;没有,出一个 yaml 文本框
      links:
        type: list
        item: {type: object, fields: {type: {type: enum, values: [specializes, suggested_by, questions, replaces, related]}, target: {type: ref, layer: issue}}}
      positions:
        type: list
        item: {type: object, fields: {claim: {type: ref, file: "positions/*.md"}, note: {type: string}}}
      summary: {type: text}
  - pattern: positions/*.md
    format: markdown
    required: false
    edit: append                   # 已有的只能在末尾续写;新建随意
    label: 立场
    name: 主张                      # pattern 里 * 那一段让用户填的名字叫什么
    template: "\n\n## 论证\n"
```

词汇表就这些,前端只实现这些:

| 项 | 取值 | 前端怎么用 |
|---|---|---|
| `format` | `markdown` / `yaml` / `text` | 选编辑器:markdown 文本框(带预览)、yaml 字段表单或文本框、纯文本框 |
| `required` | bool | 建对象表单里默认展开、不能留空提交;改对象时没有删除按钮 |
| `edit` | `full` / `append` / `none` | full 整体可编辑;append 旧内容只读、下面一个追加框,保存时发「旧内容 + 追加」;none 只读 |
| `name` | 字符串 | 只对含 `*` 的 pattern:新建按钮的标签「新建 <label>」,弹出输入框问「<name>」,文件名 = pattern 把 `*` 换成输入 |
| `template` | 字符串 | 新建这个文件时的初始内容 |
| `fields` | 键 → 字段 | 只对 `format: yaml`;字段类型见下 |

字段类型:`string`、`text`(多行)、`enum {values}`、`ref {layer}`(对端对象的 path,前端给一个搜索选择)、`ref {file}`(本目录里匹配 pattern 的文件名,前端给下拉)、`list {item}`、`object {fields}`。不做数字、日期、嵌套更深的东西;需要的层写 `format: yaml` 不带 `fields`,前端给文本框,校验在 check。

**schema 里没有的**:`manager.json`(机制文件,系统的);跨文件约束;层序;行为(没有行为)。

---

## 3. 前端拿 schema 做什么

一个通用的**目录编辑器**,对所有层一样用,前端代码里不再出现 `layer === 'issue'` 这种写法(只读渲染除外,§5)。

**建对象**:表单 = path 输入框 + 按 `files` 顺序列出所有 `required` 的固定文件,各自按 `format` 出编辑器、按 `template` 预填;非必需的固定文件折叠成「添加 <label>」;含 `*` 的 pattern 是「新建 <label>」按钮。提交 = `POST` 一批 `files`。

**改对象**:目录里每个已有文件一个编辑区,按它匹配到的 pattern 决定 `format` / `edit`:
- `full`:整体编辑,保存发新内容;
- `append`:旧内容灰显只读,下面一个追加框,保存发「旧内容 + 换行 + 追加」——「加论证」就是这个,不需要专门的动作;
- `none`:只显示。
- 非 `required` 的文件有删除按钮(发 `null`);
- 每个含 `*` 的 pattern 有「新建 <label>」——「加立场」就是这个。

**yaml 带 `fields`**:出字段表单;`ref {file}` 的下拉选项来自当前目录里匹配那个 pattern 的文件名(所以「排序」就是从已有立场里挑,挑不到不存在的);保存时前端把表单序列化回 yaml。用户手写 yaml 的入口也留着(切到文本框)。

**dry-run**:表单内容变化后防抖调 `?dry_run=1`(§4),把 check 的理由显示在对应文件旁边;保存按钮在 dry-run 不过时禁用。这样「立场只增不改」不是保存失败后的 toast,是编辑时就看到的提示。dry-run 也只是提前告诉,真正提交时还会再过一遍。

**提交主题**:表单给一个可选的「这次改动做了什么」输入,发 `subject`;不填就是 `write / edit <path>`。

---

## 4. API

| 端点 | 变化 |
|---|---|
| `GET /api/collections/layers` | 每层多一个 `schema` 字段,就是 §2 那份(JSON) |
| `POST` / `PUT /api/collections/{layer}/{path}?dry_run=1` | 走完 diff 和 check 不提交;返回 `{"ok": true}` 或 `{"ok": false, "reason": "…"}`(200,不是 422——它不是失败,是询问) |
| 其余 | 不变。写入口仍然只有 `files` |

服务层:`put()` 多一个 `dry_run` 开关,算完 changes、跑完 check 就返回。

---

## 5. 前端只特化「怎么看」,不特化「怎么写」

写的一侧全部走 §3 的通用编辑器。读的一侧允许按层渲染:issue 的立场按 `meta.positions` 排、卡片的 `context` 显示在标题下、origin 直接渲染 markdown。规则:**特化只能产生展示,不能产生写入**。这样后端改规则,前端最多是展示不够好看,不会写出被拒的东西。

---

## 6. 内置层的 schema

**origin**:`files: []`,`edit: full`,`format` 按扩展名猜(`.md` markdown、`.yaml/.yml` yaml、其余 text);没有目录,path 就是文件。

**card**:

```yaml
layer: card
files:
  - {pattern: readme.md, format: markdown, required: true, edit: full, label: 正文, template: ""}
  - pattern: meta.yaml
    format: yaml
    required: false
    edit: full
    label: 语境与关联
    fields:
      context: {type: string}
      links: {type: list, item: {type: ref, layer: card}}
      issue: {type: ref, layer: issue}
```

**issue**:§2 那份。

---

## 7. 用户层

用户层的类同样实现 `schema()`。基类给一个**默认实现**:从 `files: list[str]` 推——每个 pattern 一项,`format` 按扩展名猜,`required: false`,`edit: full`,`label` 就是 pattern,`name` 就是 `*`。所以只写了 `check` 的用户层也能得到一个能用的通用表单,只是没模板、没字段表单;想要更好的界面就把 `schema()` 写出来。

---

## 8. 漂移怎么防

`schema` 和 `check` 是同一份规则的两种说法,会漂。三道保险:

1. 写在同一个类里,改一处看得见另一处。
2. 测试:每个层,按 schema 的 `required` + `template` 建出来的目录必须过 `check`;含 `*` 的 pattern 用 `name` 造一个文件加进去也必须过;标 `append` 的文件改正文必须被拒。这几条对内置层和 `<home>/layers/*.py` 里的用户层一起跑。
3. 前端不拿 schema 判合法性,只拿它画控件;合法性永远问 check(dry-run 和真提交)。就算漂了,后果是「界面画错了控件」,不会是「写进去了不该写的」。

---

## 9. 有意不定的事

- **`title` 除了 `dirname` 要不要支持「某文件某键」**:目前所有层都是目录名当标题,先不加。
- **`ref {layer}` 的选择器**:前端做成搜索框还是目录树,看使用感受。
- **append 的粒度**:现在是「末尾续写」;要不要限定「只能加一个列表项」,等 issue 用起来再说。
- **schema 要不要也进 `collections.json`**:不进。它是代码的投影,运行时从类里读,和 `check` 一起随文件走。
