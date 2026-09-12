# layers —— 一个层是 `Layer` 接口的一个实现:一个 check

```python
class Layer(ABC):                                   # base.py
    name: str                                       # = 分支 layer/<name>、后缀 .<name>、提交前缀 [<name>]
    files: list[str]                                # 目录里允许的文件(给人看的清单;真正的规则在 check 里)
    @abstractmethod
    def check(self, changes: list[Change], after: dict[str, bytes]) -> str | None: ...   # None = 过;str = 理由(原样报给调用方,422)

Change(path, old, new)     # 这次提交对一个对象目录的 diff:目录内相对路径;old=None 新增,new=None 删除
after                      # 改完之后这个目录的全部文件
```

形态(后缀、目录、路径拆分)从 `name` 派生,写在基类;子类只管 `name` / `files` / `check`。层无状态,一个实例服务所有对象。
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
| **origin**(`Origin`) | 没有目录:任何不带后缀的路径就是一个文件(覆盖 `suffix` / `split`) | 不校验,永远过 |
| **issue**(`Issue`;schema `Issue.Meta` 挂在类里) | `readme.md`(必需)/ `meta.yaml` / `positions/<主张>.md` | 别的文件拒;`readme.md` 不能删;立场文件新建随意、改只能在末尾追加、不能删(改名 = 删 + 建,也不行);`meta.yaml` 按 `Meta`:`links[].type` 五种、`(type, target)` 不重复、`positions[].claim` 必须是已有立场、多余键拒 |
| **card**(`Card`;schema `Card.Meta`) | `readme.md`(必需)/ `meta.yaml` | 别的文件拒;`readme.md` 不能删;`meta.yaml` 只有 `context` / `links[]` / `issue`,多余键拒 |

标题都是目录名,文件里不再写标题。「加一个立场」= PUT 一个新的 `positions/<主张>.md`;「加一条论证」= PUT 那个文件、末尾多一行;「排序」= PUT `meta.yaml`。提交主题由调用方给(`subject`),不给就是 `write / edit <path>`。

## 用户层:`<home>/layers/<name>.py`

和内置层一模一样:一个 `.py`,里面一个 `Layer` 子类。启动时载入(`load_user`),排在内置层之上,按文件名;`collections.json` 里自动补一项 `{"name", "builtin": false}`,新分支从始祖出发。

```python
# ~/.memory.talk/layers/experiment.py
from memorytalk.backend.services.collections.layers import Layer, appended_only, load_yaml

class Experiment(Layer):
    name = "experiment"
    files = ["readme.md", "result.yaml", "runs/*.md"]

    def check(self, changes, after):
        for c in changes:
            if c.path == "readme.md" and c.new is None:
                return "readme.md 不能删"
            ...
        return None if "readme.md" in after else "缺 readme.md"
```

没有 YAML、没有 schema 编译、没有加层的端点:加一层 = 放一个文件,重启。文件里没有 `Layer` 子类,或 `collections.json` 里记着的层找不到文件,启动即报错。

## 要加一个内置层

和用户层一样写,只是文件放在这个目录、实例放进 `__init__.py` 的 `BUILTIN`(最底在前)。已有仓库启动时 `Repo.ensure_layers` 会把缺的层补进 `collections.json`。
