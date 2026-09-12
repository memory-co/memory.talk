# layers —— 层是目录的校验器:LayerSpec 描述什么、用户提交什么、两者怎么对上

三件事分开说:① `LayerSpec` 描述的是**一个对象目录允许长什么样**;② 用户通过 API 提交的是**目录里的文件**;③ 二者之间的映射(提交的文件怎么校验、落在哪、读回来长什么样)。最后按 origin / issue / card 各给一份对照。

## ① LayerSpec:一个层的声明(`_spec.py`)

```python
LayerSpec(name, files=[FileRule(...), ...], title="dirname" | "<文件>:<字段>", behaviors={...}, view=fn, raw=False)
FileRule(pattern, format, required=False, fields={}, model=<pydantic>, check=fn)
```

| 字段 | 描述的是 | 决定了什么 |
|---|---|---|
| `name` | 层名 | 分支 `layer/<name>`;对象目录后缀 `.<name>`;提交前缀 `[<name>]` |
| `files[]` | **目录清单**:每一条一种文件 | 目录里允许放哪些路径(`pattern` 可用 `*` 通配);清单外的文件一律拒 |
| `files[].format` | 那种文件的形态:`markdown` / `markdown+frontmatter` / `yaml` / `json` / `text` | 怎么解析、怎么序列化;markdown / text 原样,其余解成键值表 |
| `files[].required` | 必需与否 | 缺了整批拒;建对象时没给的必需 markdown / text 文件自动给空文件(git 里目录得有东西) |
| `files[].model` / `fields` | pydantic 模型 / 给 API 看的字段表 | yaml / json / frontmatter 文件里允许哪些键、哪些必填、什么类型;多余的键也拒 |
| `files[].check` | 跨文件的额外校验 `(rel, parsed, 全目录 parsed)` | 比如 issue 的 `meta.positions[].claim` 必须是 `positions/` 下存在的文件 |
| `title` | 标题从哪来 | `dirname`(目录名)或 `card.md:title`(某文件的某字段);目录 / tree 里显示的名字 |
| `behaviors` | `{动作名: 函数}` | `POST /act/<layer>/<动作>/<path>` 能调哪些**快捷方式**;它们走通用写入的同一个门 |
| `view` | `(parsed files, path) -> body` | GET 时把目录里的几个文件合成一个视图;没有就 `{相对路径: 解析结果}`(单文件层直接给那个文件的解析结果) |
| `raw` | origin 专用 | 没有目录、没有清单、不校验,路径本身就是文件 |

## ② 用户提交的格式(API)

对象的 URL 里 `path` 是**不带后缀**的逻辑路径(`memory.talk/配置/该走文件还是环境变量`),后缀由层加。

| 请求 | 请求体 | 说明 |
|---|---|---|
| `POST /api/collections/{layer}/{path}` 建 | `{"files": {"<相对路径>": "<内容>", …}, "reason"?}` | 目录里的文件。没给的必需文本文件补空 |
| 同上,简写 | `{"data": {字段…}}` | **只对清单里只有一个带字段文件的层**(card、单文件用户层):按字段写那个文件,正文用 `body` 键。多文件的层(issue)给 `data` → 400 |
| 同上,origin | `{"content": "原文"}` | |
| `PUT /api/collections/{layer}/{path}` 改 | `{"files": {"a.md": "新内容", "b.md": null}}` | 只动提到的文件,`null` 删;`data` 是字段合并;`content` 整体替换 |
| `DELETE …/{layer}/{path}` | 无 | 删整个目录 / origin 文件 |
| `POST /api/collections/act/{layer}/{action}/{path}` | 该行为自己定义的 JSON | 行为把 payload 翻成一批文件改动,再走上面同一个门 |

## ③ 映射:提交 → 校验 → 落盘 → 读回

```
用户提交 files(或 data → 由唯一的带字段文件 serialize 成 files)
   │  CollectionsService.put():读出目录现有文件,套上这批改动
   │  spec.validate(整个目录)                      ← 清单外文件 / 格式错 / 缺必填键 / 多余键 / 缺必需文件 / check 不过 → 422
   ▼
每个文件落到 <path>.<name>/<相对路径>
   │  Repo.commit(layer, …)                        ← 守卫:这些路径按后缀该归哪层?已被别的层占了没?
   ▼
layer/<name> 一个提交 + stack 一个 merge 节点

读:目录里的文件各按 FileRule.parse 解开 → spec.view 合成(或 {相对路径: 解析结果})→ GET 的 body;title 按 spec.title
```

守卫的规则来自 `CollectionsService.layer_of_path`:仓库路径里含 `.<name>/` 的归那一层,一个都不含的归 origin。「后缀」既是形态也是归属。

## 三个内置层对照

### origin(`origin.py`)

```python
LAYER = LayerSpec(name="origin", raw=True)
```

| | |
|---|---|
| 提交 | `{"content": "任意文本"}` |
| 校验 | 无 |
| 落盘 | `<path>`,原样 |
| 读回 `body` | 原文字符串 |
| 归属 | 所有不带 `.<层>/` 的路径 |

### issue(`issue.py`)—— 多文件目录

```python
LAYER = LayerSpec(name="issue", title="dirname", view=view, files=[
    FileRule("readme.md",      "markdown", required=True),
    FileRule("meta.yaml",      "yaml",     model=Meta, check=check_meta),     # links[] / positions[] / summary
    FileRule("positions/*.md", "markdown", check=check_position),           # 文件名 = 主张
], behaviors={"position": …, "argue": …, "link": …, "rank": …})
```

| | |
|---|---|
| 提交 | `{"files": {"readme.md": "背景…", "positions/只用环境变量.md": "为什么…\n\n## 论证\n- 够用", "meta.yaml": "links: [...]\npositions: [{claim: 只用环境变量, note: …}]\nsummary: …"}}`;`{}` 也行(只有空 readme) |
| 校验 | 三种文件之外的路径拒;`meta.yaml` 按 `Meta`(`links[].type` 五种、`(type, target)` 不重复、`positions[].claim` 必须是已有立场);立场文件名非空不含 `/` |
| 落盘 | `<path>.issue/readme.md` `meta.yaml` `positions/<主张>.md`;标题 = 目录名 |
| 读回 `body` | `{"readme", "positions": [{"claim", "note", "body", "arguments": [一行一条]}](按 meta.positions 排,没排的按文件名), "links", "summary"}` |
| 行为 | `position(claim, body?)` 新建立场文件;`argue(claim, comment)` 往 `## 论证` 下追加一行;`link(type, target)` / `rank(positions[], summary?)` 改 `meta.yaml` |

谁、何时不在文件里,在 git(每个行为一次提交,信息 `[issue] argue <path>#<主张>: …`)。

### card(`card.py`)—— 单文件

```python
class Card(BaseModel):            # extra=forbid
    title: str; context: str = ""; links: list[str] = []; issue: str | None = None; body: str = ""

LAYER = LayerSpec(name="card", title="card.md:title", files=[FileRule("card.md", "markdown+frontmatter", required=True, model=Card)],
                  behaviors={"discuss": discuss})
```

| | |
|---|---|
| 提交 | `{"data": {"title": "…", "body": "…", "context"?, "links"?, "issue"?}}`,或 `{"files": {"card.md": "---\ntitle: …\n---\n\n正文"}}` |
| 校验 | `Card`:缺 `title` 或多余键 → 422 |
| 落盘 | `<path>.card/card.md`:frontmatter(YAML)+ 正文 |
| 读回 `body` | `{"title", "context", "links", "issue", "body"}` |
| 行为 | `discuss(issue, readme?)`:新建一个 issue,卡的 `issue` 指过去;两个提交各在自己的层 |

## 用户层(`_user.py`)

同一个 `LayerSpec`,规则从 YAML 来。两种写法:

```yaml
layer: experiment                 # 目录清单写法
title: dirname
files:
  readme.md:   {format: markdown, required: true}
  result.yaml: {format: yaml, fields: {verdict: {type: string, required: true}, issue: {type: ref, layer: issue}}}
  "runs/*.md": {format: markdown}
```

```yaml
layer: decision                   # 单文件简写 = 目录里只有 decision.md
format: markdown+frontmatter      # 或 json
title: title
fields:
  title: {type: string, required: true}
  tags:  {type: "list[string]"}   # list[...] 要加引号
```

字段类型只有 `string / int / bool / ref / list[string] / list[ref]`;有字段的文件用 `pydantic.create_model` 现造模型(多余键拒);没有行为。schema 通过 `POST /api/collections/layers` 交上去,内嵌进仓库根 `collections.json`,启动时 `_load_layers` 从那里读回。

## 要加一个内置层

1. `<name>.py`:写清 `files=[FileRule(...)]`(有字段的给 pydantic model,跨文件约束给 `check`),`LAYER = LayerSpec(...)`。
2. 行为(可选):`(collections, path, payload, ctx)`,用 `collections.file()` 读、`collections.put()` 写,自己起提交信息。读视图(可选):`view=(parsed, path) -> body`。
3. 放进 `__init__.py` 的 `BUILTIN`(最底在前)。已有仓库启动时 `Repo.ensure_layers` 会把缺的层补进 `collections.json`。
