# Collections API

认知层。层 = 一个 `Layer` 子类的 `check(diff, after)`(内置 origin / issue / card;用户层是 `~/.memory.talk/layers/*.py`);对象 = 带后缀的目录 `<path>.<层>/`,里面一组文件,放在树的任何位置,标题就是目录名;origin = 不带后缀的文件。一次写 = 对一个对象目录的一批文件改动,交给层的 check(不过 → 422 `invalid`,`message` 是理由),过了一个 `[层名]` 提交,落在 `layer/<层>` 上再 merge 进 `stack`;碰了别的层的路径被守卫拒绝(409 `guard`)。机制见 [designs collections.md](../../designs/v5/collections.md) / [collections-layer.md](../../designs/v5/collections-layer.md) / [manager.md](../../designs/v5/manager.md)。

`{path:path}` 直接放在 URL 里(可含 `/` 和中文)。固定子路径(`layers` `config` `tree` `search` `manager` `managed` `history`)先于 `{layer}`。

---

## 层

### GET /api/collections/layers

```json
[{"name": "origin", "order": 0, "builtin": true,  "suffix": null,     "files": [],                                          "description": "…"},
 {"name": "issue",  "order": 1, "builtin": true,  "suffix": ".issue", "files": ["readme.md", "meta.yaml", "positions/*.md"], "description": "…"},
 {"name": "card",   "order": 2, "builtin": true,  "suffix": ".card",  "files": ["readme.md", "meta.yaml"],                  "description": "…"},
 {"name": "experiment", "order": 3, "builtin": false, "suffix": ".experiment", "files": ["readme.md", "result.yaml", "runs/*.md"], "description": "…"}]
```

最底在前。`files` 是对象目录里允许的文件(给人看的清单,可通配);规则在各层的 `check` 里。**没有加层的端点**:用户层是 `~/.memory.talk/layers/<名>.py` 里一个和内置层一模一样的 `Layer` 子类,重启时载入、登记进 `collections.json`(一次 `[origin]` 提交)、新分支从始祖出发;`builtin: false`。怎么写见 [collections-layer.md](../../designs/v5/collections-layer.md)。

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

一层的目录:按目录树列 `{"path", "title"}`,`title` 就是路径末段(目录名)。origin 层列的是所有不带后缀的文件。

---

## 对象

### POST /api/collections/{layer}/{path}

```json
{"files": {"readme.md": "背景……", "positions/只用环境变量.md": "为什么……"}, "subject": "raise memory.talk/配置/该走文件还是环境变量", "reason": "撞见的"}
```

- `files`:目录里的文件 `{相对路径: 内容}`,至少一个。这批改动整个交给层的 `check`,不过 → 422 `invalid`,`message` 是理由(哪个文件、为什么)。
- origin 层:`{"content": "原文"}`,落成 `<path>` 这个文件。
- `subject`:提交信息的主题,不给就是 `write <path>`。`reason` 进 body。
- **201** 返回 Obj:`{"layer", "path", "title": 目录名, "files": {相对路径: 内容}}`;已存在 → 409 `exists`。

### GET /api/collections/{layer}/{path}?rev=

`files` 是目录里的文件原文(不解析、不合成视图,怎么渲染是客户端的事);origin 给 `content`。`rev=` 读历史版本(sha 来自 history)。

### PUT /api/collections/{layer}/{path}

`{"files": {"positions/乙.md": "…", "meta.yaml": null}, "subject"?, "reason"?}`:只动提到的文件,`null` 删,没变的不算(一个都没变 → 400);这批改动交给层的 check(删必需文件、改只增不改的文件 → 422)。origin `{"content"}` 整体替换。提交 `[层] edit <path>`(或 `subject`)。

### DELETE /api/collections/{layer}/{path}?reason=

删对象(整个目录)/ origin 文件。**200**,`data: null`。历史在 git。

### GET /api/collections/history/{layer}/{path}

`[{"sha", "author", "date", "subject", "body"}]`,来自 `git log layer/<层> -- <对象目录>`,新在前,最多 50。

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
