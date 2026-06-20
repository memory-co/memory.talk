# session mark

**打注解的命令** —— 对一个 session **逐 round 提交 mark**(以写代读),mark 里 `#…？` 自动建卡 / 关联老卡。这是 v4 抽卡的**写路径前端**,机制见 [`../../works/v4/session-mark.md`](../../works/v4/session-mark.md);它是 `session` 命令组下 v4 新增的子命令(`session list | tag` 沿用 v3)。

```bash
memory.talk session mark --session <session_id> [--file <path>] [--json]
```

一次调用 = **一个 round 的一份 mark 提交**。提交体是一份 **YAML**(顶层 `last_index` + `round_index` + `description` + `marks` 数组),从 `--file` 读、不给则读 **stdin**——大段自由文本走文件 / 管道,**不经 shell / JSON 转义**。

## 参数

| 参数 | 必填 | 说明 |
|---|---|---|
| `--session` | 是 | 给哪个 session 打注解;`sess_<...>` |
| `--file` | 否 | 提交体 YAML 的路径;**不给则从 stdin 读**(`cat sub.yaml \| memory.talk session mark --session …`) |
| `--json` | 否 | JSON 输出(默认 Markdown) |

## 提交体(YAML)

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
