# session mark

**打注解的命令** —— 对一个 session **逐 round 提交 mark**(以写代读),mark 里 `#…？` 自动建卡 / 关联老卡。这是 v4 抽卡的**写路径前端**,机制见 [`../../works/v4/session-mark.md`](../../works/v4/session-mark.md);它是 `session` 命令组下 v4 新增的子命令(`session list | tag` 沿用 v3)。

`session mark` 有**两种模式**:

```bash
# 模式一 · 文件 / 管道:喂一份 YAML 提交体,一次落一个 round 的 mark
memory.talk session mark --session <sid> --file <path>     [--json]
cat sub.yaml | memory.talk session mark --session <sid>    [--json]

# 模式二 · 交互:不喂 YAML,进 2-round 滑动窗口,逐轮走、逐轮标
memory.talk session mark --session <sid>                   # 终端无管道输入时自动进交互
memory.talk session mark --session <sid> --interactive
```

- **文件 / 管道模式**:把一份 YAML 提交体(顶层 `last_index` + `round_index` + `description` + `marks`)从 `--file` 或 **stdin** 喂进来,一次落**一个 round** 的 mark。大段文本走文件 / 管道、不经 shell / JSON 转义。适合 agent 一次性产出。见 [#提交体yaml文件--管道模式](#提交体yaml文件--管道模式)。
- **交互模式**:**不喂 YAML** 时进入——**逐轮滑动窗口**:一次看 2 个 round(上一轮当上下文 + 当前轮),逐轮往前走、逐轮打标,标永远落在窗口的**第二个(当前)round**。逼着**认真逐轮读**(以写代读)。见 [#交互模式](#交互模式)。

## 参数

| 参数 | 必填 | 说明 |
|---|---|---|
| `--session` | 是 | 给哪个 session 打注解;`sess_<...>` |
| `--file` | 否 | 提交体 YAML 的路径(**文件模式**);给了就不进交互 |
| `--interactive` | 否 | 强制进**交互模式**(无管道输入时本就默认进;有时想覆盖也可显式给) |
| `--json` | 否 | JSON 输出(默认 Markdown) |

## 提交体(YAML)· 文件 / 管道模式

```yaml
last_index: 41          # 乐观锁:提交时我读到的 session 最新 round index
round_index: 37         # 这份 mark 标的是哪一轮
description: 在配 pty、用户突然提 tmux 的那几轮——想搞清他到底要什么
marks:
  - mark: |
      配 pty 的时候用户突然提了 tmux。#为什么 pty 会让用户想到 tmux？
      他其实想要的是「可重连的会话」,而不是 pty 本身。
  - mark: 这段其实在排查 EMFILE,跟句柄上限有关。
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `last_index` | 是 | 提交时读到的 session 最新 round index。**乐观锁**:与 session 当前最新 round index 不一致 → 整份拒绝(见 [错误](#错误)) |
| `round_index` | 是 | 这份 mark 标的是第几轮;越界报错 |
| `description` | 是 | 这次标注的场景(为什么读这段、带着什么问题);随每条 mark 落盘 |
| `marks` | 是 | 数组,每条 `{mark: <文本>}`;**非空**。`mark` 文本里用 `#…？`(`#` 起、`？`/`?` 止)就地标问题 |
| `marks[].id` | 否 | mark id `m<n>`;**默认系统按 append 顺序分配**(`m1`→`m2`→…,session 内单调不复用)。显式给则校验单调 |

## 交互模式

不喂 YAML 时进入。把整个 session 当一段对话**回放**着读:一次只摆 **2 个 round** 在眼前——**上一轮**(上下文)+ **当前轮**——逐轮往前滑、逐轮打标。**标永远落在窗口的第二个(当前)round**;第一轮只做语境。

### 滑动窗口怎么走

- 窗口大小固定 **2**。每往前一步:**进一个 round、出一个 round**(模拟对话一轮轮播下去)。
- 第 k 步窗口 = `[round_{k}, round_{k+1}]`,上轮 `round_k` 是上下文、**当前轮 `round_{k+1}` 是要标的**(`round_index = k+1`)。
- 走法:`[r1,r2]`→标 r2 → `[r2,r3]`→标 r3 → … → `[r_{N-1}, r_N]`→标 r_N。`r1` 永远只当上下文,不被标。
- 每步你**只为当前轮写 mark**(可多行;`#…？` 就地标问题);**回车空提交 = 这轮没什么可说,跳过**(往前滑一格)。

```
$ memory.talk session mark --session sess_def456
session sess_def456 · 41 rounds · 交互打标(标当前轮 / 回车跳过 / :q 退出 / :back 回退一格)

──────── round 36 ·(上下文)────────
[assistant] 我先帮你把 pty 配上,这样就能跑交互式程序了。
──────── round 37 ·(当前 · 标这里)────────
[human] 等等,能不能直接用 tmux?

mark> 配 pty 时用户突然提 tmux。#为什么 pty 会让用户想到 tmux？
      他其实想要的是可重连会话,不是 pty 本身。
↵
✓ sess_def456#m1 · round 37 · → new card card_01jz8k2m  (#为什么 pty 会让用户想到 tmux？)

──────── round 37 ·(上下文)────────
[human] 等等,能不能直接用 tmux?
──────── round 38 ·(当前 · 标这里)────────
[assistant] tmux 是终端复用器,可重连;pty 只是底层伪终端……

mark> ↵                                   # 空提交 = 这轮跳过
（skipped round 38）

──────── round 38 ·(上下文)────────
…
```

- 每一步的 mark 走的就是 §[提交体](#提交体yaml文件--管道模式) 那套写入(落 `marks/m<n>.yaml` + `session_marks` + 解析 `#…？` 建卡),只是 `round_index` 由窗口位置自动给、`marks` 数组只含你这步写的这条。
- **`last_index` 在进交互时一次性锁定**(= 进入时 session 的最新 round index)。中途若 session 又被 sync 写了新 round → 下一步提交触发乐观锁、提示「session 长了,退出重进」(见 [错误](#错误))。
- **`description`**:进交互时问一次(或 `--description` 预给),作为这趟标注的场景,带进这趟每条 mark;不想填可空。

### 交互指令

| 输入 | 作用 |
|---|---|
| 写一段文本后回车 | 为**当前轮**落一条 mark,然后往前滑一格 |
| 直接回车(空) | 当前轮跳过(不落 mark),往前滑一格 |
| `:back` | 回退一格(看回上一窗口;**已落的 mark 不撤**,append-only) |
| `:q` | 退出交互 |

> 交互模式是**人 / agent 认真逐轮读**的工作台;要批量、可脚本化就用文件 / 管道模式。两种模式落盘完全一样(`marks/m<n>.yaml` + `session_marks` + `card_sessions`)。

## `#…？` → 自动建卡

每条 `mark` 文本里的 `#…？` 在写入时被解析、embed 撞 `cards`(issue)向量库:

- **新问题(miss)→ 建一张新卡**(`issue` = 问题文本,还没答案)。
- **老问题(hit)→ 关联**到那张已有卡。
- 两种都记一条 [`card_sessions`](../../api/v4/card-sessions.md) 出处,指 **`(session_id, mark)`**(即 `sess_<sid>#<mark>`)——出处精确到那条 mark,不只 session。

判「新 / 老」由**检索**算(miss = 惊讶 = 新卡),不靠 AI 自评。详见 [card.md §6](../../works/v4/card.md#6-写路径每轮对话怎么变成卡--旁白--惊讶--question)。

## 落地

- 每条 mark → `sessions/<source>/<bucket>/<sid>/marks/m<n>.yaml`(canonical,YAML;带 `last_index` / `description` / `round_index` / `mark` / `questions` / `created_at`)。
- 元信息 → `session_marks` 表(派生索引:`session_id` / `mark` / `round_index` / `last_index` / `created_at`),撑乐观锁 + 寻址 + 反查。
- 读回某条 mark 走 [`read sess_<sid>#m1`](read.md)(按 `#` 分片判型)。

调用的本地端点:`POST /v4/sessions/{session_id}/marks`。

## 输出

Markdown(默认):

```
✓ marked sess_def456 · round 37 · last_index 41
  m1  #为什么 pty 会让用户想到 tmux？  → new card card_01jz8k2m
  m2  (无问题)
```

`--json`:

```json
{
  "session_id": "sess_def456",
  "round_index": 37,
  "last_index": 41,
  "marks": [
    {"mark": "m1", "questions": [{"raw": "为什么 pty 会让用户想到 tmux", "card_id": "card_01jz8k2m", "is_new": true}]},
    {"mark": "m2", "questions": []}
  ]
}
```

## 错误

| 情况 | 行为 |
|---|---|
| `last_index` 与 session 当前最新 round index 不一致(标注期间又来了新 round) | `error: session advanced (last_index 41 ≠ current 43); re-read & re-mark`,exit 1(乐观锁冲突 / 409) |
| `--session` 前缀错 / session 不存在 | `error: session '<id>' not found`,exit 1 |
| `round_index` 越界 / 非整数 | `error: round_index <n> out of range`,exit 1 |
| `marks` 为空 / YAML 解析失败 | `error: marks required` / `error: invalid YAML`,exit 1 |
| 显式 `id` 跳号 / 复用已有 `m<n>` | `error: mark id must be monotonic`,exit 1 |
| 连不上服务 | `error: cannot reach server`,exit 1 |

> **状态:设计提案,未实施**(同 [session-mark.md](../../works/v4/session-mark.md))。
