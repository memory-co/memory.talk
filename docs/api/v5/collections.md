# Collections API

认知层。层 = 一份 YAML 协议(内置 origin / issue / card;用户层是 `~/.memory.talk/layers/*.yaml`),一个引擎按它校验;对象 = 带后缀的目录 `<path>.<层>/`,里面一组文件,放在树的任何位置,标题就是目录名;origin = 不带后缀的文件。一次写 = 对一个对象目录的一批文件改动,交给层的 check(不过 → 422 `invalid`,`message` 是理由),过了一个 `[层名]` 提交,落在 `layer/<层>` 上再 merge 进 `stack`;碰了别的层的路径被守卫拒绝(409 `guard`)。机制见 [designs collections.md](../../designs/v5/collections.md) / [collections-layer.md](../../designs/v5/collections-layer.md) / [manager.md](../../designs/v5/manager.md)。

`{path:path}` 直接放在 URL 里(可含 `/` 和中文)。固定子路径(`layers` `config` `tree` `search` `manager` `managed` `history`)先于 `{layer}/{path}`。

---

## 层

### GET /api/collections/layers

```json
[{"name": "origin", "order": 0, "builtin": true, "suffix": null, "description": "…",
  "protocol": {"layer": "origin", "description": "…", "object": null, "files": []}},
 {"name": "issue", "order": 1, "builtin": true, "suffix": ".issue", "description": "…",
  "protocol": {"layer": "issue", "object": {"pattern": "^(?P<name>[^/]+)\\.issue$", "name": "问题", "under": ".*", "example": "{name}.issue"},
               "files": [{"pattern": "^readme\\.md$", "label": "问题", "fixed": true, "example": "readme.md", "required": true,
                          "format": {"fields": {"links": {"type": "list", "item": {…}}, "summary": {"type": "text", …}}, "body": "markdown"}, "template": ""},
                         {"pattern": "^positions/(?P<name>[^/]+)\\.md$", "label": "立场", "name": "主张", "fixed": false, "example": "positions/{name}.md", "required": false,
                          "format": {"fields": {"links": {…}, "rank": {"type": "number", …}, "verdict": {"type": "string", …}}, "body": "markdown"}, "template": "\n\n## 论证\n"}]}},
 {"name": "card", "order": 2, "builtin": true, "suffix": ".card", "description": "…", "protocol": {…}}]
```

最底在前。`protocol` 就是这一层的 YAML(见 [collections-layer.md](../../designs/v5/collections-layer.md)),前端据此画表单:`object` 是对象目录的规则(名字正则、`name` 那段叫什么、能放在哪),`files` 每种文件的正则、`example`(`{name}` 是用户起的那段)、`fixed`(固定文件至多一个)、`required`、`format.fields`(frontmatter 字段:`string` `text` `number` `bool` `date` `enum` `ref` `list` `object`)、`format.body`、`template`。**没有加层的端点**:用户层是 `~/.memory.talk/layers/<名>.yaml`,重启时载入、登记进 `collections.json`(一次 `[origin]` 提交);`builtin: false`。

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

### GET /api/collections/tree?path=&layer=&recursive=&candidate=

浏览的唯一接口。`items` 是这里有什么(对象折成一项,`path` 不含后缀;普通目录;origin 文件;`manager.json` / `collections.json` 不列);`layer=` 只留那一层的对象 / 文件(目录保留,可以继续往下走);`recursive=1` 往下走到底,`items` 拍平(只有对象和文件,`path` 是全路径)——「某一层的全部对象」就是 `?layer=card&recursive=1`;`can_create` 是这里还能建什么,`candidate=` 问一个名字行不行。

```json
{"path": "memory.talk/配置", "layer": null,
 "items": [{"name": "配置", "path": "memory.talk/配置", "kind": "dir", "layer": null},
           {"name": "旧方案.md", "path": "memory.talk/配置/旧方案.md", "kind": "file", "layer": "origin"},
           {"name": "该走文件还是环境变量.issue", "path": "memory.talk/配置/该走文件还是环境变量", "kind": "object", "layer": "issue"}],
 "can_create": {"objects": [{"layer": "issue", "pattern": "…", "name": "问题", "under": ".*", "example": "{name}.issue", "can": true},
                            {"layer": "card", "example": "{name}.card", "name": "标题", "can": true}],
                "files": [{"layer": "origin", "can": true}]},
 "candidate": {"name": "要不要加配置文件.issue", "matches": {"layer": "issue", "name": "要不要加配置文件"}, "exists": false, "can": true}}
```

`path` 是对象目录(或它的子目录)时,`layer` 是那一层,`can_create.objects` 为空(对象不嵌套),`can_create.files` 按这一层的文件种类逐种回答:`example` / `label` / `fixed` / `existing`(已有的)/ `can` / `reason`(固定文件已存在);子目录只列能落到这里的种类。此时 `candidate` 问的是对象目录内的文件路径:匹配哪一种、存不存在、能不能建。

### GET /api/collections/recent?layer=&path=&limit=20&before=

最近改过的对象,像 `git log` 一样往下翻:沿 `stack` 的时间线往回走,每次提交碰的文件按后缀折回对象,**每个对象只出现一次**(落在它最近那次提交上),新的在前。

```json
{"items": [{"layer": "issue", "path": "memory.talk/配置/该走文件还是环境变量", "title": "该走文件还是环境变量", "files": ["positions/只用环境变量.md"],
            "sha": "…", "subject": "[issue] position …: 只用环境变量", "author": "alice", "date": "…"},
           {"layer": "card", "path": "memory.talk/配置/配置只来自环境变量", "title": "…", "files": ["readme.md"], …},
           {"layer": "origin", "path": "memory.talk/资料.md", "title": "资料.md", "files": [], …}],
 "next": "<sha>"}
```

`files` 是那次提交里这个对象动了哪些文件(origin 为空)。`layer=` 只看一层,`path=` 只看某个目录之下。`limit`(1–200)条一页,`next` 是下一页的游标(不透明字符串)——再请求时原样带上 `before=<next>`;`null` = 到底了。去重是全局的:翻到后面的页不会再看到前面出现过的对象。机制文件(`collections.json` / `manager.json`)的提交不算。

### GET /api/collections/search?q=&layer=

`git grep -n -i` 整个 stack;`layer=` 只留某层。返回 `[{"layer", "path", "file", "line", "text"}]`,一行一条。

---

## 对象

### POST /api/collections/{layer}/{path}

```json
{"files": {"readme.md": "---\nsummary: 先这样\n---\n\n背景……", "positions/只用环境变量.md": "---\nrank: 1\nverdict: 够用\n---\n\n为什么……"},
 "subject": "raise memory.talk/配置/该走文件还是环境变量", "reason": "撞见的"}
```

- `files`:目录里的文件 `{相对路径: 内容}`,至少一个;每个文件 = frontmatter 字段 + 正文。这批改动按层的协议校验:路径要匹配某一种文件、对象目录名 / 位置合规、frontmatter 只能有声明的字段且类型对、`required` 的文件不能缺;不过 → 422 `invalid`,`message` 是理由(哪个文件、为什么)。
- `?dry_run=1`:只校验不提交,返回 `{"ok": true}` 或 `{"ok": false, "reason": "…"}`(状态码不变)。
- origin 层:`{"content": "原文"}`,落成 `<path>` 这个文件。
- `subject`:提交信息的主题,不给就是 `write <path>`。`reason` 进 body。
- **201** 返回 Obj:`{"layer", "path", "title": 目录名, "files": {相对路径: 内容}}`;已存在 → 409 `exists`。

### GET /api/collections/{layer}/{path}?rev=

`files` 是目录里的文件原文(不解析、不合成视图,怎么渲染是客户端的事);origin 给 `content`。`rev=` 读历史版本(sha 来自 history)。

### PUT /api/collections/{layer}/{path}

`{"files": {"positions/乙.md": "…", "positions/甲.md": null}, "subject"?, "reason"?}`:只动提到的文件,`null` 删,没变的不算(一个都没变 → 400);这批改动按协议校验(删必需文件、字段不合 → 422);`?dry_run=1` 同上。origin `{"content"}` 整体替换。提交 `[层] edit <path>`(或 `subject`)。

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
