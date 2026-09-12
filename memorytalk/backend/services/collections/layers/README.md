# layers —— 一个层是怎么定义的,以及 origin / issue / card 各收什么

一个层 = **名字 + 形态 + schema + 行为**,全部装进一个 `LayerSpec`(`_spec.py`)。内置层各一个文件(`origin.py` / `issue.py` / `card.py`),用户层由 `_user.py` 把 YAML 字段表翻成同样的 `LayerSpec`。`CollectionsService` 只认 `LayerSpec`,不认识具体哪一层——所以加一层不用改 service。

## 来龙去脉:一次写入从 API 到 git

```
POST /api/collections/{layer}/{path}   {"data": {...}}  或 origin 的 {"content": "..."}
        │
        ▼
CollectionsService.create(layer, path, data)
        │  spec = self.layer(layer)                     ← 找到这一层的 LayerSpec
        │  content = spec.serialize(data)               ← ① 用 spec.model(pydantic)校验;不合 → 422 invalid
        │                                                  ② 按 spec.format 编码成字节(json / markdown+frontmatter / 原样)
        │  repo_path = spec.body_path(path)             ← ③ 决定落在仓库哪个文件(后缀目录 + 本体文件名)
        ▼
Repo.commit(layer, message, {repo_path: content})      ← ④ 守卫:repo_path 按后缀该归哪层、是否被别的层占了
        │
        ▼
layer/<layer> 分支一个提交  +  stack 一个 merge 节点
```

读是反过来:`spec.path_of(repo_path)` 认出是不是本层的对象,`spec.parse(bytes)` 解回对象,`spec.title_of(obj)` 给目录用的标题;issue 还有一个 `view` 把现算字段(up / down / credence)加上。

所以「传入什么格式才满足要求」由两样东西决定:**`format`**(落成什么文件)和 **`model`**(哪些字段、哪些必填)。下面分层说。

## origin —— 原样的文件

```python
LAYER = LayerSpec(name="origin", format="raw", builtin=True, description="…")
```

- `format="raw"`:没有后缀、没有本体文件、没有 model。`<path>` 本身就是文件,`path_of` 对任何路径都成立——**所有不带层后缀的路径都归 origin**。
- 传入:`{"content": "原文字符串"}`。写什么落什么,不校验、不改。
- 落盘:`memory.talk/资料.md` → 仓库里就是 `memory.talk/资料.md`。
- 没有行为。它是最底层,上层改不动它的文件(守卫)。

## issue —— JSON 对象 + 一组行为

```python
class Issue(BaseModel):
    question: str                              # 必填
    origin: Origin | None = None               # 出处:{work_id, rounds} 或 {origin: "<origin 路径>"}
    card: str | None = None                    # 争完写成的卡 / 挂在哪张卡上(card 的 path)
    positions: list[Position] = []             # 立场;每个立场下有 arguments(论证)和 spawned_works
    links: list[IssueLink] = []                # IBIS 边:{type, target}
    created_at: str                            # 自动填

LAYER = LayerSpec(
    name="issue", format="json", model=Issue, title="question", builtin=True,
    refs={"card": "card"},                     # 哪些字段是指向别的层对象的 path(给 API 的字段表标 ref)
    behaviors={"position": position, "argue": argue, "link": link, "spawn": spawn, "decide": decide},
)
LAYER.fields = fields_of(Issue, LAYER.refs)    # 从 pydantic 模型抽给 GET /layers 看的字段表
LAYER.view = read_view                         # 读视图:加 up / down / neutral / credence,立场按 credence 倒序
```

- `format="json"`:对象是目录 `<path>.issue/`,本体 `issue.json`。`title="question"` 表示目录列表用 question 当标题。
- 传入(create):`{"data": {"question": "…", "origin": {...}?}}`,只要满足 `Issue` 就行,缺 `question` → 422。`positions` / `links` 通常不在 create 时给,由行为往里加。
- 传入(update):`{"data": {"card": "…"}}`,字段合并。
- **行为**(`POST /act/issue/<action>/<path>`)是 schema 之上的领域动作:签名统一 `(collections, path, payload, ctx) -> obj`,自己 `collections.get` 读、改对象、`collections.write` 提交,提交信息自己定(`position <path>#p1: …`)。`decide` 跨两层:`[issue] decide` + `[card] write` 两个相邻提交带同一个 `Decision:` trailer,第二个失败则第一个反向提交退回。

## card —— markdown + frontmatter

```python
class Card(BaseModel):
    title: str                                 # 必填
    context: str = ""                          # 在哪成立
    links: list[str] = []                      # 相关卡的 path
    issue: str | None = None                   # 讨论页(issue 的 path)
    body: str = ""                             # 正文(markdown 层固定有这个键)

LAYER = LayerSpec(
    name="card", format="markdown", model=Card, title="title", builtin=True,
    refs={"issue": "issue", "links": "card"},
    behaviors={"discuss": discuss},
)
LAYER.fields = fields_of(Card, LAYER.refs)
```

- `format="markdown"`:对象是目录 `<path>.card/`,本体 `card.md`。`serialize` 把除 `body` 以外的字段写成 frontmatter,`body` 是正文;`parse` 反过来(list 字段在 frontmatter 里是逗号分隔,按 `fields` 的类型解回)。

  ```markdown
  ---
  title: 配置只来自环境变量
  context: memory.talk
  links: a/b, a/c
  issue: memory.talk/配置/该走文件还是环境变量
  ---

  正文……
  ```

- 传入(create / update):`{"data": {"title": "…", "body": "…", "context": "…", "links": [...]}}`。正文一律用 `body` 键,不要自己拼 frontmatter。
- 行为 `discuss`:对这张卡不同意,开一个 issue 挂上去当讨论页——`[issue] raise` + `[card] link`,同一个 `Discussion:` trailer。

## 用户层 —— 同一套东西,从 YAML 来

```yaml
layer: decision
format: markdown+frontmatter     # 或 json
title: title
fields:
  title:  {type: string, required: true}
  issue:  {type: ref, layer: issue}
  tags:   {type: "list[string]"}          # list[...] 要加引号
```

`_user.py` 用 `pydantic.create_model` 按字段表现造一个 model,和内置层走完全一样的 `serialize / parse / body_path`。类型只有 `string / int / bool / ref / list[string] / list[ref]`;没有行为。schema 通过 `POST /api/collections/layers` 交上去,内嵌进仓库根的 `collections.json`,启动时 `CollectionsService._load_layers` 从那里读回来。

## 要加一个内置层

1. 新建 `<name>.py`:写一个 pydantic model(必填字段不给默认值),造 `LAYER = LayerSpec(...)`,`LAYER.fields = fields_of(Model, LAYER.refs)`。
2. 行为(可选):函数 `(collections, path, payload, ctx) -> obj`,放进 `behaviors`。读视图(可选):`LAYER.view = fn(collections, path, obj)`。
3. 在 `__init__.py` 的 `BUILTIN` 里按层序(最底在前)放进去。已有仓库启动时 `Repo.ensure_layers` 会把缺的内置层补进 `collections.json`。
