# Collections API

认知层。层由 schema 定义(内置 origin / issue / card,可加用户层);对象 = 带后缀的目录 `<path>.<层>/`,放在树的任何位置;origin = 不带后缀的文件。每个写动作一个 `[层名]` 提交,落在 `layer/<层>` 上再 merge 进 `stack`;碰了别的层的路径被守卫拒绝(409 `guard`)。机制见 [designs collections.md](../../designs/v5/collections.md) / [collections-layer.md](../../designs/v5/collections-layer.md) / [manager.md](../../designs/v5/manager.md)。

`{path:path}` 直接放在 URL 里(可含 `/` 和中文)。固定子路径(`layers` `tree` `search` `manager` `managed` `history` `act`)先于 `{layer}`。

---

## 层

### GET /api/collections/layers

```json
[{"name": "origin", "order": 0, "builtin": true, "suffix": null, "body": null, "format": "raw", "title": null, "fields": {}, "behaviors": [], "description": "…"},
 {"name": "issue",  "order": 1, "builtin": true, "suffix": ".issue", "body": "issue.json", "format": "json", "title": "question",
  "fields": {"question": {"type": "string", "required": true, …}, "card": {"type": "ref", "ref": "card", …}, …},
  "behaviors": ["argue", "decide", "link", "position", "spawn"]},
 {"name": "card",   "order": 2, "builtin": true, "suffix": ".card", "body": "card.md", "format": "markdown", "title": "title", "behaviors": ["discuss"], …}]
```

最底在前。用户层排在内置层之上,`behaviors` 为空。

### POST /api/collections/layers

加一个用户层:一份 YAML 字段表(格式见 [collections-layer.md §2](../../designs/v5/collections-layer.md))。

```json
{"name": "decision", "schema_yaml": "layer: decision\nformat: markdown+frontmatter\ntitle: title\nfields:\n  title: {type: string, required: true}\n  issue: {type: ref, layer: issue}\n", "reason": ""}
```

**201** 返回 LayerInfo。副作用:`schemas/decision.yaml` 进最底层(一个 `[origin]` 提交)、根上的 `layers` 文件加一行、新分支 `layer/decision` 从始祖出发。重启后仍在。已存在 → 409。类型只有 `string` `int` `bool` `"list[string]"` `ref` `"list[ref]"`(带 `[` 的要加引号)。

---

## 树、检索、目录

### GET /api/collections/tree?path=

浏览一个目录:对象折成一项(`kind: object`,`path` 不含后缀)、普通目录、origin 文件。`manager.json` / `layers` / `schemas/` 不列。

```json
[{"name": "配置", "path": "memory.talk/配置", "kind": "dir", "layer": null},
 {"name": "旧方案.md", "path": "memory.talk/配置/旧方案.md", "kind": "file", "layer": "origin"},
 {"name": "该走文件还是环境变量.issue", "path": "memory.talk/配置/该走文件还是环境变量", "kind": "object", "layer": "issue"}]
```

### GET /api/collections/search?q=&layer=

`git grep -n -i` 整个 stack;`layer=` 只留某层。返回 `[{"layer", "path", "file", "line", "text"}]`,一行一条。

### GET /api/collections/{layer}?dir=

一层的目录:按目录树列 `{"path", "title"}`。`title` 是 schema 的 title 字段,没有就用路径末段。origin 层列的是所有不带后缀的文件。

### GET /api/collections/{layer}/recall?dir=

同上,渲染成缩进文本(`text/plain`),给 agent 直接读。work 开工注入的是 `GET /api/works/{id}/recall`(默认 card 层)。

---

## 对象

### POST /api/collections/{layer}/{path}

```json
{"data": {"question": "配置该走文件还是环境变量?", "origin": {"work_id": "work_a", "rounds": [3]}}, "reason": "撞见的"}
```

- 非 origin 层:`data` 按 schema 校验(不合 → 422 `invalid`),落成 `<path>.<层>/<本体文件>`。
- origin 层:`{"content": "原文"}`,落成 `<path>` 这个文件。
- **201** 返回 Obj:`{"layer", "path", "title", "body"}`;已存在 → 409 `exists`。提交 `[层] write <path>`。

### GET /api/collections/{layer}/{path}?rev=

`body` 是按 schema 解析后的对象(issue 附现算的 `up / down / neutral / credence`,立场按 credence 倒序);origin 是原文字符串。`rev=` 读历史版本(sha 来自 history)。

### PUT /api/collections/{layer}/{path}

`{"data": {...}, "reason"}` 字段合并(`null` 不动;markdown 层正文用 `body` 键);origin `{"content"}` 整体替换。提交 `[层] edit <path>`。

### DELETE /api/collections/{layer}/{path}?reason=

删对象(整个目录)/ origin 文件。**204**。历史在 git。

### GET /api/collections/history/{layer}/{path}

`[{"sha", "author", "date", "subject", "body"}]`,来自 `git log layer/<层> -- <对象目录>`,新在前,最多 50。

---

## 行为(schema 之上的领域动作)

### POST /api/collections/act/{layer}/{action}/{path}

payload 是 JSON 对象,按行为不同。返回该行为的结果(issue 的行为返回 issue 读视图;card 的 `discuss` 返回新 issue)。层没有这个行为 → 404 `no_action`。

**issue**

| action | payload | 提交 |
|---|---|---|
| `position` | `claim`, `origin?`, `reason?` | `[issue] position <path>#p<n>: …` |
| `argue` | `position`, `stance` (1/0/-1), `comment?`, `evidence?` `{work_id, rounds, origin}`, `work_id?`, `reason?` | `[issue] argue <path>#p<n> +1` |
| `link` | `type` (specializes / suggested_by / questions / replaces / related), `target`, `reason?` | `[issue] link …` |
| `spawn` | `position`, `work_id`, `reason?` | `[issue] spawn <path>#p<n> -> <work_id>` |
| `decide` | `position`, `card` (卡的 path), `title?`, `body?`, `context?`, `reason?` | **两个相邻提交**:`[issue] decide <path>#p<n> -> card <card>` + `[card] write <card>`,同一个 `Decision:` trailer;第二个失败则第一个用反向提交退回。卡已存在 → 409 |

**card**

| action | payload | 提交 |
|---|---|---|
| `discuss` | `issue` (新 issue 的 path), `question`, `origin?`, `reason?` | **两个相邻提交**:`[issue] raise <issue>: …`(`card` 指回这张卡)+ `[card] link <path> -> issue <issue>`,同一个 `Discussion:` trailer |

---

## manager

### GET /api/collections/manager?path=

这个路径(目录、对象 path 或文件)归谁管:往上找最近的 `manager.json`。没有 → `null`。

```json
{"dir": "memory.talk", "work": "work_…"}
```

### PUT /api/collections/manager?path=

`{"work": "work_…", "reason": ""}`。在这个目录(或对象自己的目录)下写 `manager.json`。它是机制文件:在 `.issue/` 里随 `[issue]` 提交,在普通目录里随最底层提交;它自己的变动不投递。

### DELETE /api/collections/manager?path=&reason=

删这个目录的 `manager.json`,解析回到上一级。**204**。

### GET /api/collections/managed?work=

`work=` 给了:这个 work 管的所有对象(按继承链解析);不给:**没人管**的对象。

### 投递

Collections 里每个提交触碰的路径 → 解析 manager → 一条写进 `works/<work>/inbox.jsonl`(`GET /api/works/{id}/inbox`);没人管 → `~/.memory.talk/unmanaged.jsonl`;请求带的 `X-Memory-Talk-Work` 等于 manager work 时不投(自己造成的)。
