# layers —— 一个层就是一个校验函数

```python
check(changes: list[Change], after: dict[str, bytes]) -> str | None     # None = 过;str = 拒绝的理由(原样报给调用方,422)
Change(path, old, new)     # 这次提交对一个对象目录的 diff:目录内相对路径;old=None 新增,new=None 删除
after                      # 改完之后这个目录的全部文件
```

这是一个 pre-receive hook 的形状。层不认识 API、不认识读法、没有行为:**写就是写文件,层只负责说这批文件改动过不过。**
看 diff 才能表达「只增不改」「不能删」;看 `after` 才能做跨文件约束(`meta.positions[].claim` 得是已有的立场)。

## 从 API 到 git

```
POST / PUT /api/collections/{layer}/{path}   {"files": {"<相对路径>": "<内容>" | null}, "subject"?, "reason"?}
   │  CollectionsService.put():读出目录现有文件,和 files 比出 changes,算出 after(没变的不算,一个都没变 → 400)
   │  layer.check(changes, after)            ← 拒 → 422,message 就是那句理由
   ▼
每个文件落到 <path>.<layer>/<相对路径>  →  Repo.commit(守卫:路径按后缀归哪层)  →  layer/<name> 一个提交 + stack 一个 merge 节点
读:GET 给 {"layer", "path", "title": 目录名, "files": {相对路径: 内容}};origin 给 "content"。不解析、不合成视图,怎么渲染是客户端的事。
```

`manager.json` 是机制文件,任何层的任何目录都允许,不进 check。

## 三个内置层

| 层 | 目录里允许 | check 的规则 |
|---|---|---|
| **origin**(`origin.py`) | 没有目录:任何不带后缀的路径就是一个文件 | 不校验,永远过 |
| **issue**(`issue.py`) | `readme.md`(必需)/ `meta.yaml` / `positions/<主张>.md` | 别的文件拒;`readme.md` 不能删;立场文件新建随意、改只能在末尾追加、不能删(改名 = 删 + 建,也不行);`meta.yaml` 按 `Meta`:`links[].type` 五种、`(type, target)` 不重复、`positions[].claim` 必须是已有立场、多余键拒 |
| **card**(`card.py`) | `readme.md`(必需)/ `meta.yaml` | 别的文件拒;`readme.md` 不能删;`meta.yaml` 只有 `context` / `links[]` / `issue`,多余键拒 |

标题都是目录名,文件里不再写标题。「加一个立场」= PUT 一个新的 `positions/<主张>.md`;「加一条论证」= PUT 那个文件、末尾多一行;「排序」= PUT `meta.yaml`。提交主题由调用方给(`subject`),不给就是 `write / edit <path>`。

## 用户层(`_user.py`)

一份 YAML 清单编译成一个 `check`:

```yaml
layer: experiment
files:
  readme.md:   {format: markdown, required: true}
  result.yaml: {format: yaml, fields: {verdict: {type: string, required: true}, issue: {type: ref, layer: issue}}}
  "runs/*.md": {format: markdown, append_only: true}
```

规则:清单外的路径拒;`required` 的不能缺、不能删;`append_only` 的只能在末尾追加;`format: yaml / json` 的解开按 `fields` 校验(必填、类型、多余键拒),`markdown / text` 不看内容。字段类型:`string` `int` `bool` `ref` `list[string]` `list[ref]`。
schema 通过 `POST /api/collections/layers` 交上去,内嵌进仓库根 `collections.json`,启动时 `_load_layers` 从那里读回;`GET /layers` 原样给出。

## 要加一个内置层

1. `<name>.py`:写一个 `check(changes, after)`,`LAYER = Layer(name, check, files=[给人看的清单], description)`。
2. 放进 `__init__.py` 的 `BUILTIN`(最底在前)。已有仓库启动时 `Repo.ensure_layers` 会把缺的层补进 `collections.json`。
