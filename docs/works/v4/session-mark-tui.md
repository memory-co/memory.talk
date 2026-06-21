# 交互式 `session mark` —— TUI 方案设计(v4)

> **状态:已实现(v1.1.x)。** 交互模式现为 **`rich` 渲染 + `questionary` 输入的客户端 step 走查**([`cli/_mark.py`](../../../memorytalk/cli/_mark.py)),即本篇方案 B。命令契约见 [`../../cli/v4/session.md`](../../cli/v4/session.md) 的 `## session mark`。

---

## 1. 它到底要干什么(需求)

把一个已落库的 session 当对话**回放**着读,逐 round 往前走、逐 round 打 mark(以写代读):

- **2-round 滑动窗口**:一次摆**上一轮(上下文)+ 当前轮(要标的)**;**从第一轮起**逐轮走,每步进一 round、出一 round。
- **逐轮交互**:对当前轮 —— 写一条 comment(可多行,含 `#…？`)/ 空 = 留空(仍记一条 `{index}` 占覆盖)/ `:back` 回退 / `:q` 退出。
- **`comment` 的 `#…？` grounding 在本轮 `index`**:交互模式不让用户手填 grounding;`#…？` 默认 ground 在它那条 round 的 `index`。
- **`m<n>` 服务端自动分配**:提交体**不带** id —— 服务端 `next_seq`(COUNT+1)给这份 mark 配号(第一遍 `m1`、续标 `m2`…)。客户端不再 `GET …/marks` 续号、不再本地 mint `m<n>`。
- **`last_index` 乐观锁**:进入时一次性锁定 = session 当前 round 数;提交时若 session 已被 sync 写了新 round → 409 → 提示退出重进。
- **一份提交 = 一份 mark**:窗口走完(或中途 `:q`)后,把收集到的 `rounds[]` 一次 `POST /v4/sessions/{id}/marks`(文件模式与交互模式落盘完全一致)。
- **覆盖率 ≥ 90%**:从第一轮逐轮走到底自然 100%;中途 `:q` 若覆盖 < 90% → 拦下、提示还差几轮。
- **健壮**:空 session / 单 round / 超长 round 文本 / 提交期 session 前进,都不能崩。

本质是**引导式的线性 REPL**(走一遍、边走边写),不是多窗格的复杂应用。这一点决定了选型。

---

## 2. 方案候选(关键:`rich` + `questionary` 已是依赖)

`pyproject.toml` 现有:**`rich>=13`**(渲染,`cli/_render.py` / `util/console.py` 在用)、**`questionary>=2`**(交互提示,setup wizard 在用;它**基于 `prompt_toolkit`**,所以 prompt_toolkit 已被传递引入)。所以「全屏 TUI」也**不必引新依赖**。

| 方案 | 新依赖 | 全屏? | 可测性 | 跟现有栈一致? | 评价 |
|---|---|---|---|---|---|
| **A. 纯 stdlib REPL**(`input()`) | 无 | 否 | 好 | 一般 | 现状的更糙版;渲染丑、无多行编辑。**否决** |
| **B. `rich` 渲染 + `questionary` 输入(REPL)** | **无**(都已有) | 否(滚动式) | **好** | **完全一致** | round 用 rich `Panel` 漂亮渲染;mark 用 questionary 多行文本;`:back`/`:q`/跳过在 loop 里。**← 推荐** |
| C. `prompt_toolkit` 全屏 `Application` | 无(已传递引入,需显式声明) | **是**(持久屏 + 状态栏) | 中 | 一致(底层就是它) | 真·全屏,但**靠终端转义序列绘屏 → 对 AI 是负资产**(escape-code 乱码,没法经 tool-use 驱动);对人也过度设计。**否决(见 §3)** |
| D. `textual` 框架 | **新增大依赖** | 是 | 很好(Pilot) | 不一致 | 同 C:全屏转义对 AI 不友好 + 新大依赖;留给未来复杂多窗格(explore 工作台)。**当前否决** |
| E. `curses` | 无(stdlib) | 是 | 差 | 不一致 | 低层、脆、难测、Windows 要额外包。**否决** |

---

## 3. 关键:主要消费者是 **AI** —— 这改变结论

交互式 `session mark` 后续**主要给 AI 用**(LLM 经 tool-use 调命令、读 stdout / JSON),人是次要。这条直接否掉「全屏」:

- **全屏 TUI(C/D)对 AI 是负资产**:prompt_toolkit / Textual 靠**终端转义序列**绘屏,AI 经 tool-use 读到的是 escape-code 乱码,**没法驱动**。→ **排除 C/D**。
- **「以写代读」对 AI 打折**:逐 round 窗口本是逼**人**别跳读;对 AI,跳读产生的噪声**下游检索 miss/hit 已兜底过滤**(见 [card.md §6](card.md)),所以「强制逐轮」对 AI 不是非有不可。

**两条路子(都走同一个批量端点 `POST /v4/sessions/{id}/marks`,不加新 API)**:
1. **YAML 批量(文件 / 管道,★ 已实现)**:`read <sid>` 拿结构化 rounds → 组 marks YAML → 一次 `--mark` / 管道提交。完全结构化、最贴合 AI tool-use(一问一答)。**AI 主路径 + 可脚本化。**
2. **交互式 step 标注(客户端走查,方案 B)**:CLI 把 session **一轮轮摆出来**(2-round 窗口:上一轮上下文 + 当前轮),你**逐轮 step 着标**;marks 在**本地累积**(自动配 `m<n>` + 自动填窗口 `indexes`),走完**一次性发同一个批量端点**。**前端体验是 step 的,后端就是那一份批量提交** —— 不加新端点、不加服务端草稿态。给人用顺手,也是「能 step 标注」的那条路。

> **明确否决:服务端 stepping 协议。** 不做「每个 round 一个离散 HTTP 端点 + 服务端逐步草稿态」那套(API step)。step 的状态只活在**客户端走查 loop** 里,提交还是一份批量——简单、原子(一份提交一个乐观锁)。

### 修订结论
- **路子 1 = YAML 批量**(已实现):AI 主路径 + 脚本化;`--json` 结构化输出(哪些 `#…？` 建新 / 连老卡、`card_id`)打磨好。
- **路子 2 = 交互式 step 标注**(方案 B,`rich` 渲染 + `questionary` 输入的客户端走查):本地累积、批量提交,**这就是「能 step 标注」的路子**(本篇要实现的)。
- **不建全屏 TUI(C / D)**——转义序列对 AI 是负资产、对人也过度设计。
- **不做服务端 stepping 协议**——step 只在客户端,后端永远是批量提交。

---

## 4. 架构(路子 2:交互式 step 标注 = 客户端走查 over 批量端点)

```
session mark --session <sid>            (无 --mark → 交互)
  │
  ├─ GET /v4/read {id:<sid>}            → 取 rounds(只读)
  ├─ last_index = len(rounds)           乐观锁基线(进入时锁定)
  ├─ description = questionary.text(...) 问一次场景(可空)
  │
  ├─ 滑窗 loop  k = 0..N-1(从第一轮起,每轮记一条):
  │     渲染窗口:rich.Panel(prev=r[k-1] 淡色上下文,k=0 时无) + rich.Panel(cur=r[k] 当前·标这里)
  │     ans = questionary.text("comment>", multiline=True)   # 多行;含 #…？
  │     · 空        → 记 {index:当前轮}(无 comment,占覆盖),k++
  │     · ":back"   → k--(再走到同一轮会覆盖那一条)
  │     · ":q"      → 跳出
  │     · 文本      → 记 {index:当前轮, comment:ans},k++
  │
  ├─ 覆盖率 < 90% → 拦下、提示还差几轮,不提交
  └─ POST /v4/sessions/<sid>/marks {last_index, description, rounds:[...]}   ← 不带 id,服务端配 m<n>
        · 200 → fmt_mark_result(服务端分配的 m<n> + 哪些 #…？ 建新/连老卡)
        · 409 → "session 期间被写入(last_index 41≠当前 43);退出重进"
```

要点:
- **渲染** `rich`:`Panel` 包每个 round(speaker/role + 文本,超长中截);当前轮高亮(标题 `round 37 · 标这里`),上一轮淡色(`round 36 · 上下文`)。
- **输入** `questionary.text(multiline=True)`:一条 comment 天然多行;命令 `:back`/`:q` 用文本前缀识别。
- **`#…？` grounding 自动**:= 它那条 round 的 `index`(comment 里的 `#…？` 默认 ground 在本轮)。想 ground 在别的轮 → 走文件模式的主动声明 `issues: [{issue, indexes}]`。
- **`m<n>` 服务端分配**:提交体不带 id;`:back` 覆盖同 index 的条目(按 index 去重,提交前升序重排)。
- **提交时机**:**一份提交 = 一份 mark**(走完一次性 POST)——简单、原子(一份提交一个乐观锁)。

---

## 5. 测试策略

- **单元**:喂一串「输入序列」驱动 loop(注入 `ask_comment` 输入 seam),断言**最终构造的提交体**(`rounds[]` 从 index 1 起、严格递增、**不带 id**、空行也记一条、`:back` 回退后覆盖同 index)。
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
