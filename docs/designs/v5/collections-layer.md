# collections layer —— 怎么设计一个自己的层(v5 设计)

> **状态:已实施。** 一个层 = `Layer` 接口的一个实现,一个 `check(diff, after) -> None | str`;用户层就是 `~/.memory.talk/layers/<名>.py` 里一模一样的子类,启动时载入,没有 YAML、没有加层的端点。实现见 `memorytalk/backend/services/collections/layers/`(README 讲契约和三个内置层的规则)。[collections.md](collections.md) 说 issue 和 card 只是 Collections 里两个内置的 layer。本篇讲**怎么加一层**。总定位见 [README.md](README.md)。

相关:
- v5 collections(层即 collectbase 的 layer;Collections 是认知层的容器): [collections.md](collections.md)
- v5 manager(任何层的任何目录都可以放 `manager.json`): [manager.md](manager.md)
- v5 issue / card(两个内置层,照着看就是范例): [issue.md](issue.md) / [card.md](card.md)
- collectbase 的 `layers` 锚定文件(memory.talk 对应的是仓库根的 `collections.json`): [cli.md](https://github.com/memory-co/collectbase/blob/main/docs/v2/works/cli.md)

---

## 1. 一句话:一个层 = 回答四个问题 + 写一个 .py

你想在认知层里记一种新东西——决策记录、实验日志、人物档案、外部文档摘要——就是加一个层。加一个层要回答四个问题:

| 问题 | 答案落在哪 |
|---|---|
| **叫什么** | 层名:`collections.json` 的 `layers[]` 里一项、分支 `layer/<名>`、提交前缀 `[名]` |
| **住哪** | 路径:这个层的文件都在哪个目录下(和别的层不相交) |
| **长什么样** | 一个对象是一个**目录**;层是一个**校验函数**:这次提交对目录的 diff 进去,过 / 不过出去。允许哪些文件、哪些只增不改、字段怎么校验,都是这个函数的事 |
| **排在哪** | 层序:它在 `collections.json` 的 `layers[]` 里的位置——比谁更接近记录、比谁更接近结论 |

落下来就是 **`~/.memory.talk/layers/<名>.py` 里一个 `Layer` 子类**——和内置的 issue / card 一模一样的写法;重启时载入,`collections.json` 的 `layers[]` 自动多一项(名字 + `builtin: false`),一次最底层的提交,`git log collections.json` 就是层的变化史。要写代码,但只写一个方法:`check`。

---

## 2. 四个问题怎么答

### 叫什么

一个小写英文单词,单数:`decision`、`experiment`、`person`。它同时是层名、分支名、提交前缀、**目录后缀**、API 路径段——一个名字到处用,别起两个。

### 住哪

**哪都行。** 层不占目录([collections.md §1](collections.md)):一个对象是**一个带后缀的目录** `<名>.<层>/`,放在树的任何位置——`memory.talk/配置/重审配置方案.decision/` 和它讨论的 `.issue/`、写出来的 `.card/`、引用的原文文件并排在同一个文件夹里。「这个路径归哪层」看后缀就知道;`manager.json` 的继承链按目录树走,一个主题文件夹一个 manager,管它下面所有层的东西。

对象是目录,不是文件——这样它可以由几个文件组成(issue 是 `readme.md` + `meta.yaml` + `positions/*.md`),自己身上能放 `manager.json`。目录里**允许放什么**由 schema 定(下一条),schema 没列的文件进不来。

### 长什么样:一个校验函数

层就是 `check(changes, after) -> None | str`:`changes` 是这次提交对一个对象目录的 diff(相对路径、改前、改后;改前为空是新增,改后为空是删除),`after` 是改完的整个目录;返回 None 过,返回一句话拒、那句话原样报给调用方。看 diff 才能说「只增不改」「不能删」,看 after 才能做跨文件约束。这是一个 pre-receive hook 的形状。

内置层和用户层是同一个接口、同一种写法,区别只是文件放在哪:

```python
# ~/.memory.talk/layers/decision.py
import fnmatch
from memorytalk.backend.services.collections.layers import Layer, appended_only, load_yaml

class Decision(Layer):
    name = "decision"                                   # = 后缀 .decision、分支 layer/decision、提交前缀 [decision]
    files = ["readme.md", "meta.yaml", "notes/*.md"]    # 给人看的清单;规则在 check 里
    description = "一个决定:定了什么、否了什么、什么时候重审"

    def check(self, changes, after):
        for c in changes:
            if c.path == "readme.md":
                if c.new is None:
                    return "readme.md 不能删"
            elif c.path == "meta.yaml":
                if c.new is not None and "chosen" not in load_yaml(c.new):
                    return "meta.yaml 要有 chosen"
            elif fnmatch.fnmatchcase(c.path, "notes/*.md"):
                if c.old is not None and c.new is not None and not appended_only(c.old, c.new):
                    return f"{c.path}:只能在末尾追加"
            else:
                return f"{c.path}:decision 目录里只能有 readme.md / meta.yaml / notes/*.md"
        return None if "readme.md" in after else "缺 readme.md"
```

想校验多严都行——pydantic、正则、跨文件——都是你这个方法里的事;系统不认识字段、类型、引用,它只问一句「过不过」。标题**一律是目录名**,文件里不写标题。`manager.json` 是机制文件,任何层的任何目录都允许,不用管。

### 排在哪

collectbase 的层是有序的:下面的更接近记录、上面的更接近结论,**上层改不动下层**。你的层放哪,按它「从谁派生、谁从它派生」:

```
上   card       ← 争完的结论
     decision   ← 你的层:一个决定,引用 issue、指向 card;它由 issue 派生,card 由它派生
     issue      ← 争的过程
下   origin     ← 事实:外部材料,永远最底([origin.md](origin.md))
```

规则很简单:**你的对象引用谁,就排在谁上面**。引用是「我从它来」;排在它上面,改自己就碰不到它。反过来被谁引用,就排在谁下面。两边都有(像上面的 decision)就夹在中间。都没有,放最上。

---

## 3. 系统替你做什么:通用的那一套

写完 `check`,你的层立刻有了:

| 能力 | 怎么来的 |
|---|---|
| **写(建 / 改 / 删)** | 一次写 = 对一个对象目录的一批文件改动(`files`,`null` 删),算出 diff 交给你的 check,过了一次 `[名]` 提交;`/api/collections/<名>/<path>` 一套通用端点,内置层和用户层同一个门 |
| **读 / 列** | 目录里的文件原文;目录按目录树列标题(= 目录名) |
| **历史** | `git log layer/<名>`、`git log -- <路径>`;读任意历史版本 |
| **检索** | `git grep` 这一层的路径 |
| **manager** | 任何目录放 `manager.json`,这一层的变动就打到那个 work([manager.md](manager.md)) |
| **层的守卫** | 提交必须声明 `[名]`,碰了别的层的路径当场拒绝 |

这些对内置层和用户层**一视同仁**——issue 和 card 只是文件放在包里而不是 `~/.memory.talk/layers/`。

---

## 4. 系统不替你做什么:行为、视图、派生

**没有行为**,内置层也没有。issue 的「加立场」就是新建一个文件,「加论证」就是往一个文件末尾加一行,「排序」就是改 `meta.yaml`——都是普通提交,check 保证它们只能这么做(比如论证只能追加)。要「一件事跨两层」(争完写卡),那就是两个提交,agent 在 manager work 里顺序做;提交主题由调用方给(`subject`),所以历史里照样能看出是 `position …` 还是 `argue …`。

**没有视图、没有现算**:读就是文件本身。issue 的立场怎么排、卡的链接怎么展开,是客户端(CLI / 前端 / agent)读了文件自己的事。层管的只有一件事:这批改动过不过。

---

## 5. 两个例子

### decision:把「一个决定」立成一层

issue 争完写卡,那个「决定」本身现在只是两个提交上的一个 trailer。有的团队想把它立起来——记谁定的、为什么、否掉了什么、什么时候可以重审:

```
layers:      origin, issue, decision, card  ← 夹在中间
形态:        <名>.decision/decision.md       ← 放在它相关的 issue / card 旁边
check:       readme.md 必需;meta.yaml 要有 chosen,可带 rejected[] / issue / cards[] / review_after
行为:        无。「做一个决定」= 建 decision + 写 card,两个提交;标题是目录名
manager:     某个主题文件夹的 manager.json → 一个「定期重审决定」的 work;review_after 到了,agent 在收件箱里看到它
```

### experiment:实验日志

跑一次基准、试一个方案,过程在 work 的 rounds 里,但「这次实验测了什么、结论是什么」值得单独记:

```
layers:      origin, issue, card, experiment ← 放最上:它引用 issue(为哪个立场做的),没人引用它
形态:        <名>.experiment/experiment.md   ← 放在它验证的那个 .issue/ 旁边
check:       readme.md 必需;result.yaml 要有 verdict;runs/*.md 只能追加
行为:        无。实验做完 = 建一个 experiment;给立场加论证是另一个 `[issue]` 提交,那一行里写上这个 experiment 的 path
```

两个例子的共同点:**它们都只是目录 + 引用**,没有一处需要代码;而且都跟它们相关的 issue、card、原文放在同一个文件夹里。不同点在层序——decision 被 card 引用所以夹中间,experiment 谁也不引用它所以放最上。

---

## 6. 改层、删层

- **改规则**:改那个 `.py`,重启。放宽随时放;收紧要先把老对象迁过来——那是一次 `[名]` 提交,历史里看得见。规则本身不在仓库里,在文件里(想留历史就把 `~/.memory.talk/layers/` 自己放进 git)。
- **加层**:放一个 `.py`,重启;`collections.json` 自动多一项,新分支从始祖出发。
- **删层**:分支留着不动;把 `.py` 拿走的同时要把 `collections.json` 里那一项删掉(否则启动报错——这是故意的,防止层无声消失),通用端点就不再暴露它,文件和历史都在。**不删对象**。

---

## 7. 这篇有意不定的事

- ~~schema 文件放哪、归哪层~~:已定——没有 schema 文件;规则在 `~/.memory.talk/layers/<名>.py` 里,`collections.json` 只记名字和 `builtin`。
- **schema 语言**:上面用的是 YAML 字段表。要不要直接用 JSON Schema(表达力强、工具多,但对人不友好)——倾向 YAML 字段表 + 少数约定,真不够再说。
- **引用要不要校验存在**:`decision.issue` 指向一个不存在的 issue,写的时候拒绝还是放行。倾向写时校验存在、删时不级联(同 [collections.md §7](collections.md))。
- **通用端点的形状**:`/api/collections/<层>/<id>` 一套,内置层的 `/api/issues/…` `/api/cards/…` 是不是它上面的别名。
- **用户层要不要能声明「只增不改」**:issue 的立场是 append-only,那是代码保证的。用户层能不能在 schema 里写一句 `append_only: true` 让系统替它挡——能做,但先不做;真要不可变,git 已经给了历史,「不许改」多半是过度设计。
