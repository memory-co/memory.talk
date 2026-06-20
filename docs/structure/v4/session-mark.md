# SessionMark

**对一个 session 打的注解** —— mark 是 session 的附属,不是一等对象。**一份 mark 提交标注的是整个 session**(不绑定单一 round);一条 mark = 一段「以写代读」的感悟,`mark` 文本里 `#…？` 自动建卡。正文落 YAML 文件(canonical),元信息进 `session_marks` 表(派生索引)。

机制见 [`../../works/v4/session-mark.md`](../../works/v4/session-mark.md);命令见 [`../../cli/v4/session.md#session-mark`](../../cli/v4/session.md#session-mark);出处边 see [CardSession](card-session.md)。

## 寻址:`<session_id>#<mark>`,不是一等 id

mark **没有独立前缀 id**(没有 `mark_`、没有 `IdKind.MARK`)。它是 session 的附属,id `m<n>`(`m` + session 内递增序号),寻址 `<session_id>#<id>`:

```
sess_def456#m1    ← sess_def456 的第 1 条 mark(盘上 marks/m1.yaml)
sess_def456#m2    ← 第 2 条
```

`read sess_def456#m1` 按 `#` 分片判型,定位「这个 session 的 mark m1」。

## 文件(canonical):`marks/m<n>.yaml`

```
sessions/<source>/<sid[0:2]>/<sid>/
  rounds.jsonl                ← round 正文(沿用 v3)
  marks/
    m1.yaml                   ← 一条 mark 一个文件,文件名 = id
    m2.yaml
    …
```

```yaml
# marks/m1.yaml
last_index: 41                # 标这批 mark 时 session 的最新 round index(乐观锁基线 + 当时情况)
description: 在配 pty、用户突然提 tmux 的那几轮——想搞清他到底要什么
mark: |                       # 自由感悟正文;#…？ 就地标问题
  配 pty 时用户突然提了 tmux。#为什么 pty 会让用户想到 tmux？
  他其实想要可重连会话。
issues:                    # 写入时解析 #…？ + 撞库的结果(canonical)
  - issue: 为什么 pty 会让用户想到 tmux
    card_id: card_01jz8k2m
    is_new: true
created_at: 2026-06-16T08:30:00Z
```

| 字段 | 说明 |
|---|---|
| `last_index` | 提交时读到的 session 最新 round index;乐观锁基线(写入时与 session 当前最新 round index 比,不一致拒绝) |
| `description` | 这次标注的场景(随提交带进每个 mark 文件) |
| `mark` | 自由文本感悟;`#…？`(`#` 起、`？`/`?` 止)= 就地标的问题 |
| `issues[]` | 解析 `#…？` + 撞 `cards` 库的结果:`{issue, card_id, is_new}`(新卡 / 关联老卡)。**canonical**——`card_sessions` 由它派生 |
| `created_at` | ISO 8601 |

- **append-only**:写一次不动;改主意 = 加新 `m<n>`。
- **不进向量库**:mark 本身不检索;进 `cards` 向量库的是它 `#…？` 出来的问题(卡)。

## 表(派生索引):`session_marks`

mark 的元信息(序号 / round / 乐观锁基线 / 时间)进表,撑乐观锁、寻址、反查;**正文不进表**(留 YAML)。

```sql
CREATE TABLE session_marks (
  session_id  TEXT NOT NULL,        -- 哪个 session
  mark        TEXT NOT NULL,        -- mark id(m1 / m2 …);寻址 = session_id#mark
  last_index  INTEGER NOT NULL,     -- 标这条 mark 时 session 的最新 round index(乐观锁基线)
  created_at  TEXT NOT NULL,
  PRIMARY KEY (session_id, mark)
);
CREATE INDEX idx_session_marks_session ON session_marks(session_id);  -- 列 session 的 mark / 取最大序号
```

- **无 FOREIGN KEY**(SQLite 派生索引,容忍悬空;canonical 是 `marks/*.yaml`,表丢了能重建)。
- `PRIMARY KEY (session_id, mark)`:`m<n>` 在 session 内唯一。
- 取「下一个 mark 序号」「session 当前 `last_index` 基线」都走这张表,不必扫文件。

## 乐观锁:`last_index`

提交一份 mark 时,系统拿提交里的 `last_index` 跟 session 当前最新 round index 比:

- **相等** → 放行(落 `marks/m<n>.yaml` + 插 `session_marks` 行)。
- **不等**(标注期间又来了新 round)→ **拒绝**(409 / conflict),带新 round 重读再标。

`last_index` 同时是「这条 mark 标在 session 长到第几轮」的记录——事后回看「当时是个什么情况」。

## 跟 card_sessions 的分工

| 表 | 管什么 |
|---|---|
| `session_marks` | mark 自己的元信息(序号 / round / `last_index` / 时间) |
| [`card_sessions`](card-session.md) | mark → card 的出处边(`card_id` + `session_id` + `mark`;**无 `position`、无 `indexes`**——答案级出处在 [`position_sessions`](position-session.md)) |

`session_marks` 是「有哪些 mark」,`card_sessions` 是「哪条 mark 启发了哪张卡」;两者都从 `marks/*.yaml`(canonical · `issues[]`)派生。
