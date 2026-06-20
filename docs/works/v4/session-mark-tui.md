# 交互式 `session mark` —— TUI 方案设计(v4)

> **状态:设计提案(待实现)。** 回答一个具体问题:`memory.talk session mark`(不带 `--mark`)的**交互模式**该用什么做。当前是 `click.prompt` 行式 loop([`cli/_mark.py`](../../../memorytalk/cli/_mark.py),179 行);本篇定方案再升级。命令契约见 [`../../cli/v4/session.md`](../../cli/v4/session.md) 的 `## session mark`。

---

## 1. 它到底要干什么(需求)

把一个已落库的 session 当对话**回放**着读,逐 round 往前走、逐 round 打 mark(以写代读):

- **2-round 滑动窗口**:一次摆**上一轮(上下文)+ 当前轮(要标的)**;每步进一 round、出一 round。
- **逐轮交互**:对当前轮 —— 写一条 mark 文本(可多行,含 `#…？`)/ 空 = 跳过 / `:back` 回退 / `:q` 退出。
- **`indexes` 自动填**:当前窗口的 round 区间(这条 `#…？` grounding 的轮次)——交互模式不让用户手填。
- **`m<n>` 顺序分配**:API 要求 `id` **显式必填、单调不复用**(见 [session-marks.md](../../api/v4/session-marks.md)),所以 CLI 进入时先 `GET …/marks` 拿当前最大序号,逐条 `m<n+1>`。
- **`last_index` 乐观锁**:进入时一次性锁定 = session 当前 round 数;提交时若 session 已被 sync 写了新 round → 409 → 提示退出重进。
- **批量提交**:窗口走完(或中途 `:q`)后,把收集到的 marks 一次 `POST /v4/sessions/{id}/marks`(文件模式与交互模式落盘完全一致)。
- **健壮**:空 session / 单 round / 超长 round 文本 / 提交期 session 前进,都不能崩。

本质是**引导式的线性 REPL**(走一遍、边走边写),不是多窗格的复杂应用。这一点决定了选型。

---

## 2. 方案候选(关键:`rich` + `questionary` 已是依赖)

`pyproject.toml` 现有:**`rich>=13`**(渲染,`cli/_render.py` / `util/console.py` 在用)、**`questionary>=2`**(交互提示,setup wizard 在用;它**基于 `prompt_toolkit`**,所以 prompt_toolkit 已被传递引入)。所以「全屏 TUI」也**不必引新依赖**。

| 方案 | 新依赖 | 全屏? | 可测性 | 跟现有栈一致? | 评价 |
|---|---|---|---|---|---|
| **A. 纯 stdlib REPL**(`input()`) | 无 | 否 | 好 | 一般 | 现状的更糙版;渲染丑、无多行编辑。**否决** |
| **B. `rich` 渲染 + `questionary` 输入(REPL)** | **无**(都已有) | 否(滚动式) | **好** | **完全一致** | round 用 rich `Panel` 漂亮渲染;mark 用 questionary 多行文本;`:back`/`:q`/跳过在 loop 里。**← 推荐** |
| C. `prompt_toolkit` 全屏 `Application` | 无(已传递引入,需显式声明) | **是**(持久屏 + 状态栏) | 中(PipeInput 可测,较繁) | 一致(底层就是它) | 真·全屏:顶部窗格放 2-round、底部多行编辑 + 状态栏。**最贴近「全 TUI」,但代码量/测试成本高**。若确需持久屏再上 |
| D. `textual` 框架 | **新增大依赖** | 是 | 很好(Pilot) | 不一致 | 现代 widget 框架、最适合**复杂**多窗格 + 未来 explore 工作台;**当前线性流 overkill** |
| E. `curses` | 无(stdlib) | 是 | 差 | 不一致 | 低层、脆、难测、Windows 要额外包。**否决** |

---

## 3. 推荐:**B —— `rich` 渲染 + `questionary` 输入的引导式 REPL**

理由:
1. **零新依赖**:`rich` + `questionary` 都已在用,跟 setup wizard 同栈,风格统一。
2. **匹配交互本质**:这是线性「走一遍」流程,不是多窗格应用;全屏框架(C/D)的持久屏/widget 对它是过度设计。
3. **可测**:`questionary` 输入可在测试里喂(monkeypatch / `DummyInput`),提交体能断言;rich 输出可快照。跟仓库**测试文化**(600+ 测试)契合。
4. **可演进**:若以后真要持久全屏(或 explore 工作台变重),底层 `prompt_toolkit` 已在,可平滑升到方案 C,不返工。

> **何时改投 C/D**:若用户明确要「持久全屏、不滚屏、实时状态栏」,升到 **C(prompt_toolkit 全屏 Application)**——底层依赖已具备,只是多写布局/键绑定 + 测试。**D(Textual)** 只在 explore 抽卡工作台演化成复杂多窗格 TUI 时才值得引入。本设计**先落 B**,把 C 留作记录在案的升级路径。

---

## 4. 架构(方案 B)

```
session mark --session <sid>            (无 --mark → 交互)
  │
  ├─ GET /v4/read {id:<sid>}            → 取 rounds(只读)
  ├─ last_index = len(rounds)           乐观锁基线(进入时锁定)
  ├─ GET /v4/sessions/<sid>/marks       → 当前最大 m<n>,后续 m<n+1> 顺序发
  ├─ description = questionary.text(...) 问一次场景(可空)
  │
  ├─ 滑窗 loop  k = 1..N-1:
  │     渲染窗口:rich.Panel(prev=r[k] 上下文) + rich.Panel(cur=r[k+1] 当前·标这里)
  │     ans = questionary.text("mark>", multiline=True)   # 多行;含 #…？
  │     · 空        → 跳过当前轮,k++
  │     · ":back"   → k--(看回上一窗口;已收集的 mark 不撤,append-only)
  │     · ":q"      → 跳出
  │     · 文本      → 收集 {id:"m<n+1>", mark:ans, indexes:窗口当前轮区间},k++
  │
  └─ 收集非空 → POST /v4/sessions/<sid>/marks {last_index, description, marks:[...]}
        · 200 → fmt_mark_result(哪些 #…？ 建新/连老卡)
        · 409 → "session 期间被写入(last_index 41≠当前 43);退出重进"
```

要点:
- **渲染** `rich`:`Panel` 包每个 round(speaker/role + 文本,超长中截 + 可展开提示);当前轮高亮(标题 `round 37 · 标这里`),上一轮淡色(`round 36 · 上下文`)。复用 `cli/_render.py` 的 round 渲染。
- **输入** `questionary.text(multiline=True)`:一条 mark 天然多行;命令 `:back`/`:q` 用文本前缀识别(或单独 `questionary.select` 给「写/跳过/回退/退出」再写文本——但纯文本前缀更快)。
- **`indexes` 自动**:= 当前窗口被标的那 round 的 index(单轮 `"37"`;若设计允许把上下文轮也算进 grounding,则 `"36-37"`——**取当前轮**,跟 doc「自动填当前阅读窗口的 round」一致)。
- **`m<n>` 显式**:CLI 负责算并填(API 不代劳),保证单调;`:back` 不回收已分配的号(append-only)。
- **提交时机**:**批量**(走完一次性 POST)——简单、原子(一份提交一个乐观锁);不做逐步提交(逐步会让 `last_index` 语义复杂)。

---

## 5. 测试策略

- **单元**:喂一串「输入序列」驱动 loop(monkeypatch `questionary.text` 返回预设值 / 用 `prompt_toolkit` 的 `create_pipe_input`),断言**最终构造的提交体**(marks 的 id 单调、indexes 对、空行跳过、`:back` 回退后覆盖)。
- **集成**:把提交体过真 `submit_marks`(已存在),验 `#…？` 建/连卡 + `card_sessions`。
- **渲染**:rich 输出快照(可选,low 价值)。
- **边界**:空 session(直接提示无可标)、单 round(无上下文轮)、`:q` 立即退出(空提交不 POST)、提交期 last_index 冲突(mock 409)。

---

## 6. 非目标 / 未来

- **不做**全屏持久 TUI(方案 C)——除非明确要;路径已留(prompt_toolkit 已在)。
- **不引** Textual(方案 D)——留给未来 explore 抽卡工作台(若它演化成复杂多窗格)。
- explore 工作台的 TUI 是**另一篇**的事,不在本设计内。

## 跟其他 works 的关系
- 写路径机制 / `#…？` / 乐观锁 / `m<n>`:[session-mark.md](session-mark.md);
- 命令契约(文件模式 + 交互模式 UX):[`../../cli/v4/session.md`](../../cli/v4/session.md)。
