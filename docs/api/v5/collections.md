# Collections API

认知层。层 = 一份**目录的校验规则**(内置 origin / issue / card,可加用户层);对象 = 带后缀的目录 `<path>.<层>/`,里面一组文件,放在树的任何位置;origin = 不带后缀的文件。一次写 = 对一个对象目录的一批文件改动,整目录按层的 schema 校验(不合 → 422 `invalid`),过了一个 `[层名]` 提交,落在 `layer/<层>` 上再 merge 进 `stack`;碰了别的层的路径被守卫拒绝(409 `guard`)。机制见 [designs collections.md](../../designs/v5/collections.md) / [collections-layer.md](../../designs/v5/collections-layer.md) / [manager.md](../../designs/v5/manager.md)。

`{path:path}` 直接放在 URL 里(可含 `/` 和中文)。固定子路径(`layers` `config` `tree` `search` `manager` `managed` `history` `act`)先于 `{layer}`。

---

## 层

### GET /api/collections/layers

```json
[{"name": "origin", "order": 0, "builtin": true, "suffix": null, "title": "dirname", "files": [], "behaviors": [], "description": "…"},
 {"name": "issue",  "order": 1, "builtin": true, "suffix": ".issue", "title": "dirname",
  "files": [{"pattern": "readme.md", "format": "markdown", "required": true},
            {"pattern": "meta.yaml", "format": "yaml", "required": false, "fields": {"links": …, "positions": …, "summary": …}},
            {"pattern": "positions/*.md", "format": "markdown", "required": false}],
  "behaviors": ["argue", "link", "position", "rank"]},
 {"name": "card",   "order": 2, "builtin": true, "suffix": ".card", "title": "card.md:title",
  "files": [{"pattern": "card.md", "format": "markdown+frontmatter", "required": true, "fields": {"title": {"type": "string", "required": true}, "issue": {"type": "ref", "ref": "issue"}, …}}],
  "behaviors": ["discuss"]}]
```

最底在前。`files` 是对象目录里允许的文件清单(`pattern` 可通配);`title` 是标题来源(`dirname` 或 `<文件>:<字段>`)。用户层排在内置层之上,`behaviors` 为空。

### POST /api/collections/layers

加一个用户层:一份 YAML schema——`files` 目录清单(每个文件的 `format` / `required` / `fields`),或单文件简写 `format` + `fields`(格式见 [collections-layer.md §2](../../designs/v5/collections-layer.md))。

```json
{"name": "decision", "schema_yaml": "layer: decision\nformat: markdown+frontmatter\ntitle: title\nfields:\n  title: {type: string, required: true}\n  issue: {type: ref, layer: issue}\n", "reason": ""}
```

**201** 返回 LayerInfo。副作用:`collections.json` 的 `layers[]` 多一项(schema 内嵌、`added_at`),一个 `[origin]` 提交;新分支 `layer/decision` 从始祖出发。重启后仍在。已存在 → 409。类型只有 `string` `int` `bool` `"list[string]"` `ref` `"list[ref]"`(带 `[` 的要加引号)。

---

## 树、检索、目录

### GET /api/collections/config

`collections.json` 本体 + 它的提交历史(层的变化史):

```json
{"config": {"version": 1, "layers": [{"name": "origin", "builtin": true}, {"name": "issue", "builtin": true}, {"name": "card", "builtin": true},
                                        {"name": "decision", "schema": {"format": "…", "fields": {…}}, "added_at": "…"}]},
 "history": [{"sha": "…", "author": "alice", "date": "…", "subject": "[origin] collections: add layer decision", "body": "Reason: …"},
             {"sha": "…", "subject": "[origin] collections: init", …}]}
```

### GET /api/collections/tree?path=

浏览一个目录:对象折成一项(`kind: object`,`path` 不含后缀)、普通目录、origin 文件。`manager.json` / `collections.json` 不列。

```json
[{"name": "配置", "path": "memory.talk/配置", "kind": "dir", "layer": null},
 {"name": "旧方案.md", "path": "memory.talk/配置/旧方案.md", "kind": "file", "layer": "origin"},
 {"name": "该走文件还是环境变量.issue", "path": "memory.talk/配置/该走文件还是环境变量", "kind": "object", "layer": "issue"}]
```

### GET /api/collections/search?q=&layer=

`git grep -n -i` 整个 stack;`layer=` 只留某层。返回 `[{"layer", "path", "file", "line", "text"}]`,一行一条。

### GET /api/collections/{layer}?dir=

一层的目录:按目录树列 `{"path", "title"}`。`title` 是 schema 的 title 字段,没有就用路径末段。origin 层列的是所有不带后缀的文件。

---

## 对象

### POST /api/collections/{layer}/{path}

```json
{"files": {"readme.md": "背景……", "positions/只用环境变量.md": "为什么……"}, "reason": "撞见的"}
```

- `files`:目录里的文件 `{相对路径: 内容}`。整目录按层的 schema 校验:清单外的文件、格式不对、缺必填键、多余键、缺必需文件 → 422 `invalid`。没给的必需 markdown / text 文件补空(`POST /issue/<path>` 带 `{}` 就是一个只有空 `readme.md` 的 issue)。
- `data`:简写,**只对目录里只有一个带字段文件的层**(card、单文件用户层)成立——按字段写那个文件,正文用 `body` 键;issue 这种多文件层给 `data` → 400。
- origin 层:`{"content": "原文"}`,落成 `<path>` 这个文件。
- **201** 返回 Obj:`{"layer", "path", "title", "files": [目录里的文件], "body"}`;已存在 → 409 `exists`。提交 `[层] write <path>`。

### GET /api/collections/{layer}/{path}?rev=

`body` 是层的读视图:card 是 `card.md` 解析后的字段 + 正文;issue 是 `{"readme", "positions": [{"claim", "note", "body", "arguments"}], "links", "summary"}`(立场按 `meta.yaml` 的 `positions` 排,没排到的按文件名);多文件用户层是 `{相对路径: 解析结果}`;origin 是原文字符串。`rev=` 读历史版本(sha 来自 history)。

### PUT /api/collections/{layer}/{path}

`{"files": {"positions/乙.md": null, "meta.yaml": "summary: 先这样"}, "reason"}`:只动提到的文件,`null` 删,改完的目录整个再校验(删必需文件 → 422)。`data` 是字段合并(`null` 不动);origin `{"content"}` 整体替换。提交 `[层] edit <path>`。

### DELETE /api/collections/{layer}/{path}?reason=

删对象(整个目录)/ origin 文件。**200**,`data: null`。历史在 git。

### GET /api/collections/history/{layer}/{path}

`[{"sha", "author", "date", "subject", "body"}]`,来自 `git log layer/<层> -- <对象目录>`,新在前,最多 50。

---

## 行为(校验器之上的快捷方式)

### POST /api/collections/act/{layer}/{action}/{path}

行为 = 预制好的一批文件改动 + 一条像样的提交信息;和直接 `PUT files` 走同一个门、过同一个校验。payload 是 JSON 对象,按行为不同;返回该层的读视图。层没有这个行为 → 404 `no_action`;对象不存在 → 404。

**issue**

| action | payload | 碰的文件 | 提交 |
|---|---|---|---|
| `position` | `claim`, `body?`, `reason?` | 新建 `positions/<claim>.md`(已有 → 409) | `[issue] position <path>: <claim>` |
| `argue` | `claim`, `comment`, `reason?` | `positions/<claim>.md` 的 `## 论证` 下追加一行(立场不存在 → 404) | `[issue] argue <path>#<claim>: <comment>` |
| `link` | `type` (specializes / suggested_by / questions / replaces / related), `target`, `reason?` | `meta.yaml` 的 `links` 追加,不重复 | `[issue] link <path> <type> <target>` |
| `rank` | `positions[]{claim, note?}`, `summary?`, `reason?` | 整体替换 `meta.yaml` 的 `positions` / `summary`(claim 必须是已有立场,否则 422) | `[issue] rank <path>: <首位 claim>` |

谁、何时不在文件里:每个行为一次提交,author = 请求的 user。

**card**

| action | payload | 提交 |
|---|---|---|
| `discuss` | `issue` (新 issue 的 path), `readme?`, `reason?` | 两个提交:`[issue] write <issue>` + `[card] link <path> -> issue <issue>`(卡的 `issue` 指过去;issue 不记卡)。issue 已存在 → 409 |

---

## manager(暂缓:路由已注释掉,等 work 实现后一起启用;service 层逻辑保留)

### GET /api/collections/manager?path=

这个路径(目录、对象 path 或文件)归谁管:往上找最近的 `manager.json`。没有 → `null`。

```json
{"dir": "memory.talk", "work": "work_…"}
```

### PUT /api/collections/manager?path=

`{"work": "work_…", "reason": ""}`。在这个目录(或对象自己的目录)下写 `manager.json`。它是机制文件:在 `.issue/` 里随 `[issue]` 提交,在普通目录里随最底层提交;它自己的变动不投递。

### DELETE /api/collections/manager?path=&reason=

删这个目录的 `manager.json`,解析回到上一级。**200**,`data: null`。

### GET /api/collections/managed?work=

`work=` 给了:这个 work 管的所有对象(按继承链解析);不给:**没人管**的对象。

### 投递

Collections 里每个提交触碰的路径 → 解析 manager → 一条写进 `works/<work>/inbox.jsonl`(`GET /api/works/{id}/inbox`);没人管 → `~/.memory.talk/unmanaged.jsonl`;请求带的 `X-Memory-Talk-Work` 等于 manager work 时不投(自己造成的)。
