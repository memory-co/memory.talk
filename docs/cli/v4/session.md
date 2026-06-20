# session

操作 backend 已落库的 session —— **元数据**(list / tag)+ **逐 round 打注解**(mark,v4 新增)。对话内容不在这读,统一走 `memory.talk read <sid>`(`read` 按前缀判型覆盖 `card_` / `pos_` / `sess_`,以及 mark 的 `sess_…#m1` 分片)。

```
memory.talk session
├── list [filters...] [--limit N] [--json]              # 沿用 v3:按多维过滤列 session
├── tag <sid> [K=V ...] [-K ...] [--json]               # 沿用 v3:查 / 加 / 删 session 的 kv 标签
└── mark --session <sid> [--file <path>] [--json]       # v4 新增:逐 round 打注解(#…？ 自动建卡)
```

需要 server 在跑;CLI 通过 HTTP 调本地端点(v4 统一 `/v4` 前缀)。

## 三个子命令的分工

| 子命令 | 干什么 | 状态 |
|---|---|---|
| `session list` | 按 source / endpoint / cwd / tag / 时间多维过滤,**只回元数据**(不回 rounds) | **沿用 v3**,行为不变 |
| `session tag` | 查 / 设 / 删 session 上的 kv 标签(PATCH 合并语义) | **沿用 v3**,行为不变 |
| `session mark` | 对 session **逐 round 提交 mark**(以写代读),mark 里 `#…？` 自动建卡 / 关联老卡 | **v4 新增** |

> **为什么这份 v4 doc 之前没有**:v4 一开始把 `session` 整条当「沿用 v3 基础设施、本目录不复制」,契约只留在 [`../v3/session.md`](../v3/session.md)。但 v4 给 `session` **加了 `mark` 子命令**(抽卡写路径前端)——它不再是纯沿用,所以这里补一份 v4 总览:`list` / `tag` 指回 v3,`mark` 是 v4 的新面。

## session list / tag(沿用 v3)

行为、参数、`--tag` 操作符、输出格式**完全照 v3**,见 [`../v3/session.md`](../v3/session.md#session-list)。v4 下**唯一变化**:CLI 打的本地端点从 `/v3/sessions` 挪到 **`/v4/sessions`**(`GET /v4/sessions` + `PATCH /v4/sessions/{sid}/tags`),命令用法一字不改。

```bash
memory.talk session list --tag status=wip --since 7d
memory.talk session tag sess_def456 project=billing -draft
```

## session mark(v4 新增)

对一个 session **逐 round 打注解**——以写代读防走神,mark 里 `#…？` 就地标问题、写入时自动建卡 / 关联老卡,出处(`card_source`)精确指那条 mark。

```bash
# 文件 / 管道:喂一份 YAML,一次落一个 round 的 mark
memory.talk session mark --session <sid> --file <path>
cat sub.yaml | memory.talk session mark --session <sid>

# 交互:不喂 YAML,2-round 滑动窗口逐轮走、逐轮标(标当前轮)
memory.talk session mark --session <sid>
```

**两种模式**:**文件 / 管道**喂一份 YAML 提交体(`last_index` 乐观锁 + `round_index` + `description` + `marks`),一次落一个 round;**交互**则进 2-round 滑动窗口——一次看上一轮 + 当前轮,逐轮往前走、标永远落在**当前(第二个)round**,逼着认真逐轮读。`last_index` 与 session 当前最新 round index 不一致 → 拒绝(标注期间又来了新 round)。

**完整契约**(提交体格式、`#…？` 语法、`m<n>` 寻址、`session_marks` / `card_sessions` 落地、错误码)见 [`session-mark.md`](session-mark.md);机制与设计推理见 [`../../works/v4/session-mark.md`](../../works/v4/session-mark.md)。

## 跟其他命令的边界

| 想做的事 | 用哪条 |
|---|---|
| 看一条 session 的原始对话 | `memory.talk read <session_id>` |
| 看某条 mark 当时标了啥 / 建了哪些卡 | `memory.talk read sess_<sid>#m1` |
| 给 session 打注解、抽卡 | `memory.talk session mark --session <sid>` |
| 按项目 / 状态找 session | `memory.talk session list --cwd … --tag …` |

> **状态**:`list` / `tag` 已随 v3 实现;`mark` 是**设计提案、未实施**(见 [session-mark.md](session-mark.md))。
