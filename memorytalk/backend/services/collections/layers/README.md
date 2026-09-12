# layers —— LayerSpec 描述什么、用户提交什么、两者怎么对上

三件事分开说:① `LayerSpec` 的每个字段是什么;② 用户通过 API 提交的格式是什么;③ 二者之间的映射(提交的东西怎么校验、落成什么文件、读回来长什么样)。最后按 origin / issue / card 各给一份对照。

## ① LayerSpec:一个层的声明(`_spec.py`)

| 字段 | 描述的是 | 决定了什么 |
|---|---|---|
| `name` | 层名 | 分支名 `layer/<name>`;对象目录后缀 `.<name>`;本体文件名 `<name>.json` / `<name>.md`;提交前缀 `[<name>]` |
| `format` | 本体文件的形态:`raw` / `json` / `markdown` | **用户提交什么键**(见 ②)、落盘怎么编码、读回来怎么解;`raw` 表示没有后缀目录,路径本身就是文件 |
| `model` | 一个 pydantic 模型(`raw` 没有) | **用户 `data` 里允许哪些字段、哪些必填、什么类型**;校验不过 → 422 `invalid` |
| `title` | `model` 里哪个字段当标题 | 目录列表 / tree 里显示的名字;没有就用路径末段 |
| `refs` | `model` 里哪些字段存的是别的层对象的 path,`{字段: 目标层}` | 只影响 `GET /layers` 字段表里的类型标注(`ref` / `list[ref]`),不做引用校验 |
| `fields` | 给 API 看的字段表,`{字段: {type, required, ref, description}}` | `GET /api/collections/layers` 的输出;内置层用 `fields_of(model, refs)` 从 model 抽出来 |
| `behaviors` | `{动作名: 函数}` | `POST /act/<layer>/<动作>/<path>` 能调哪些动作 |
| `view` (可选) | `fn(collections, path, obj) -> obj` | GET 返回前对 body 做的现算(issue 用它加 up / down / credence) |
| `builtin` / `description` | 元信息 | 只出现在 `GET /layers` |

`format` 派生出三个东西(都在 `LayerSpec` 上算,不用手写):

| format | 后缀目录 `obj_dir(path)` | 本体文件 `body_path(path)` | 例(path = `a/b`) |
|---|---|---|---|
| `raw` | 无 | `<path>` | `a/b` |
| `json` | `<path>.<name>/` | `<path>.<name>/<name>.json` | `a/b.issue/issue.json` |
| `markdown` | `<path>.<name>/` | `<path>.<name>/<name>.md` | `a/b.card/card.md` |

## ② 用户提交的格式(API)

对象的 URL 里 `path` 是**不带后缀**的逻辑路径(`memory.talk/配置/该走文件还是环境变量`),后缀由层加。

| 请求 | 请求体 | 说明 |
|---|---|---|
| `POST /api/collections/{layer}/{path}` 创建 | 非 raw 层:`{"data": {…}, "reason"?}`;raw 层(origin):`{"content": "原文", "reason"?}` | `data` 必须满足该层的 `model` |
| `PUT /api/collections/{layer}/{path}` 修改 | 同上 | `data` 是**字段合并**(没给的不动);`content` 是整体替换 |
| `DELETE …/{layer}/{path}` | 无 | 删整个对象目录 / origin 文件 |
| `POST /api/collections/act/{layer}/{action}/{path}` | 该行为自己定义的 JSON | 由 `behaviors[action]` 处理,不经 `model` 校验(行为内部自己改对象后再经 `model`) |

**只有两种键:`data`(有 schema 的层)和 `content`(origin)。** markdown 层的正文也在 `data` 里,用 `body` 键——用户永远不需要自己拼 frontmatter。

## ③ 映射:提交 → 校验 → 落盘 → 读回

```
用户提交 data / content
   │  spec.serialize(data)
   │     raw:       content 原样 → bytes
   │     json:      model.validate(data) → json.dumps
   │     markdown:  model.validate(data) → 除 body 外的字段写成 frontmatter,body 是正文
   ▼
bytes 落到 spec.body_path(path)                      ← 文件位置由 name + format 决定
   │  Repo.commit(layer, …)                          ← 守卫:这个文件按后缀该归哪层?已被别的层占了没?
   ▼
layer/<name> 一个提交 + stack 一个 merge 节点

读:spec.path_of(repo_path) 认出对象 → spec.parse(bytes) 解回 dict(经 model)→ spec.view 现算 → GET 的 body
```

守卫的规则来自 `CollectionsService.layer_of_path`:仓库路径里含 `.<name>/` 的归那一层,一个都不含的归 origin。所以「后缀」既是形态也是归属。

## 三个内置层对照

### origin(`origin.py`)

```python
LAYER = LayerSpec(name="origin", format="raw", builtin=True)
```

| | |
|---|---|
| 提交 | `{"content": "任意文本"}` |
| 校验 | 无 |
| 落盘 | `<path>`,原样 |
| 读回 `body` | 原文字符串 |
| 归属 | 所有不带 `.<层>/` 的路径 |
| 行为 | 无 |

```
POST /api/collections/origin/memory.talk/资料.md   {"content": "# 资料\n…"}
→ 仓库文件 memory.talk/资料.md
```

### issue(`issue.py`)

```python
class Issue(BaseModel):
    question: str                      # 必填
    origin: Origin | None = None       # {work_id, rounds} 或 {origin: "<origin 路径>"}
    card: str | None = None            # 争完写成的卡 / 挂在哪张卡上(card 的 path)
    positions: list[Position] = []     # 立场(由行为追加)
    links: list[IssueLink] = []        # IBIS 边(由行为追加)
    created_at: str                    # 自动

LAYER = LayerSpec(name="issue", format="json", model=Issue, title="question", refs={"card": "card"},
                  behaviors={"position": …, "argue": …, "link": …, "spawn": …, "decide": …})
LAYER.fields = fields_of(Issue, LAYER.refs)
LAYER.view = read_view
```

| | |
|---|---|
| 提交 | `{"data": {"question": "…", "origin"?: {…}, "card"?: "…"}}` |
| 校验 | `Issue`;缺 `question` → 422 |
| 落盘 | `<path>.issue/issue.json`(`Issue` 的 JSON) |
| 读回 `body` | `Issue` 的 dict + 每个立场的 `up / down / neutral / credence`,立场按 credence 倒序 |
| 行为 | `position(claim)` `argue(position, stance, comment?)` `link(type, target)` `spawn(position, work_id)` `decide(position, card, title?, body?)` |

```
POST /api/collections/issue/memory.talk/配置/该走文件还是环境变量   {"data": {"question": "配置该走文件还是环境变量?"}}
→ 仓库文件 memory.talk/配置/该走文件还是环境变量.issue/issue.json
POST /api/collections/act/issue/position/memory.talk/配置/该走文件还是环境变量   {"claim": "只走环境变量"}
→ 同一个文件里 positions 多一项 p1
```

### card(`card.py`)

```python
class Card(BaseModel):
    title: str                         # 必填
    context: str = ""                  # 在哪成立
    links: list[str] = []              # 相关卡的 path
    issue: str | None = None           # 讨论页(issue 的 path)
    body: str = ""                     # 正文

LAYER = LayerSpec(name="card", format="markdown", model=Card, title="title", refs={"issue": "issue", "links": "card"},
                  behaviors={"discuss": …})
LAYER.fields = fields_of(Card, LAYER.refs)
```

| | |
|---|---|
| 提交 | `{"data": {"title": "…", "body": "…", "context"?: "…", "links"?: […]}}` |
| 校验 | `Card`;缺 `title` → 422 |
| 落盘 | `<path>.card/card.md`:`title / context / links / issue` 写成 frontmatter,`body` 是正文 |
| 读回 `body` | `Card` 的 dict(frontmatter 解回字段,正文回到 `body` 键;`links` 逗号分隔 → list) |
| 行为 | `discuss(issue, question)`:对这张卡开讨论页 |

```
POST /api/collections/card/memory.talk/配置/配置只来自环境变量   {"data": {"title": "配置只来自环境变量", "body": "……", "links": ["a/b"]}}
→ 仓库文件 memory.talk/配置/配置只来自环境变量.card/card.md:
   ---
   title: 配置只来自环境变量
   links: a/b
   ---

   ……
```

## 跨层的行为

行为签名统一 `(collections, path, payload, ctx) -> obj`。它拿到的是 service 本身,所以可以读改多层:`issue.decide` = `[issue] decide` + `[card] write`,`card.discuss` = `[issue] raise` + `[card] link`,都是两个相邻提交带同一个 trailer(`Decision:` / `Discussion:`),第二个失败第一个反向提交退回。

## 用户层(`_user.py`)

同一个 `LayerSpec`,只是 `model` 从 YAML 字段表用 `pydantic.create_model` 现造:

```yaml
layer: decision
format: markdown+frontmatter     # 或 json
title: title
fields:
  title: {type: string, required: true}
  issue: {type: ref, layer: issue}
  tags:  {type: "list[string]"}          # list[...] 要加引号
```

类型只有 `string / int / bool / ref / list[string] / list[ref]`;markdown 格式自动带 `body`;没有行为。提交方式、落盘位置、读回格式和内置层完全一样(`<path>.decision/decision.md`)。schema 通过 `POST /api/collections/layers` 交上去,内嵌进仓库根 `collections.json`,启动时 `_load_layers` 从那里读回。

## 要加一个内置层

1. `<name>.py`:pydantic model(必填字段不给默认值)+ `LAYER = LayerSpec(...)` + `LAYER.fields = fields_of(Model, LAYER.refs)`。
2. 行为 / 读视图按需挂上。
3. 放进 `__init__.py` 的 `BUILTIN`(最底在前)。已有仓库启动时 `Repo.ensure_layers` 会把缺的层补进 `collections.json`。
