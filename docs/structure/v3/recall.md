# Recall

**无意识召回**的事件流。hook 阶段每次 `memory.talk recall hook` 调用产生一条 `RecallEvent`,记录当时的 prompt + 返回了哪些 card + 哪些被去重跳过。

## 跟 [Review](review.md) 的关系

Recall 和 Review **不是同一个对象**,但**因果链相连**:

```
[hook]  user prompts → RecallEvent 记录"展示了 K 张卡"(无判定)
                            ↓
                        LLM 在 response 里用了这些卡
                            ↓
[optional, 大多数情况不发生]
                        user/LLM 显式调 review,Review 记"对这张卡我赞 / 踩 / 中立"
```

| | Recall | Review |
|---|---|---|
| 时机 | hook 时,**LLM 还没回答** | 看完 LLM 答案之后 |
| 触发 | 自动 | 显式(几乎从不自动) |
| 是否一定发生 | 每个 user prompt 必有 | 大多数 recall **没有**后续 review |
| 单事件 ↔ 卡 | 1 事件 ↔ K 张卡(top-K) | 1 review ↔ 1 张卡 |
| 必有字段 | `prompt` / `returned_ids` / `skipped_ids` | `score` / `comment` / `indexes` |
| 论坛动力学里的角色 | **popularity 信号**(被路过过几次,卡的"分母") | **quality 信号**(被赞还是被踩,卡的"分子") |

所以**两者都参与论坛动力学**,但角色不同:
- `card.stats.recall_count`(从 RecallEvent 派生)= 这张卡被命中过几次 → popularity
- `card.stats.review_up` / `review_down` 等(从 Review 派生)= 这张卡被怎么评价 → quality
- ranking 公式同时用这两组信号

> 之前我们考虑过"合并 Recall 进 Review"(用 Review 同时承担"被展示"和"被评价"),否决理由见 [`../../cli/v3/recall.md#design-history`](../../cli/v3/recall.md#design-history)。简而言之:Review 是 append-only + 必须有 score,塞"待判定的展示记录"会破坏 Review 的核心契约,把它的信号噪音化。

Review 在 schema 上可选反向引用 RecallEvent(`review.recall_event_id`),供"是哪次 recall 后产生的判定"做 audit。**这一项在 0.9.0 范围外**,本设计不展开;先把 Recall 这边的结构定下来。

## 存储分层:file canonical + SQLite index

跟 v3 其它对象([Card](talk-card.md) / [Review](review.md) / [Session](session.md))一致的两层结构:

```
sessions/<source>/<sid[0:2]>/<sid>/recall.jsonl   ← canonical · 唯一可信源
                                                    每次 recall hook 追加一行
                                                    内容比 SQLite 完整(含 returned cards 的 insight 快照)

recall_event(SQLite 表)                          ← derived index
                                                    从 recall.jsonl 派生,只为查询速度存在
                                                    所有"事实"以 file 为准;SQLite 可丢可重建
```

**recall.jsonl 是唯一可信源**。SQLite `recall_event` 是为了查询速度建的索引,**理论上能从 file 重建**(rebuild 实现暂缓,合约先写)。如果两边 drift,以 file 为准。

> 这跟我之前坚持的"SQLite-only,不写文件层"翻了方向。前面理由是"recall 是短期数据,多一次 fsync 不划算" —— 这条不成立,因为:
> 
> 1. 之前 ("session 还没 sync 进来,path 算不出") 的核心反对理由,在方案 A 修了 session_id 之后已经不成立。session_id 在 hook 时就**正确算出来了**,目录路径是确定的,直接写就行
> 2. cards / reviews / sessions 全部是 file canonical + SQLite index 模式;让 recall 特殊化是反例外
> 3. 文件层提供 audit / portability —— 服务器死、SQLite 丢的情况下,recall 历史还在
> 4. jsonl append 不强制 fsync,实际 IO 成本可忽略

## 所有视图怎么导出

| 视图 | 从哪里读 |
|---|---|
| **dedup**(`recall hook` 决定要不要返回某 card) | SQLite: `SELECT DISTINCT j.value FROM recall_event, json_each(returned_ids) j WHERE session_id = ?` |
| **session 列表**(`recall list`) | SQLite: `SELECT session_id, COUNT(*), MAX(ts) FROM recall_event GROUP BY session_id` |
| **session 时间线**(`recall read <session_id>`) | 优先 SQLite(查询快);插入卡片快照展示时关联 cards 表 |
| **card 的累计召回数**(search/read 结果旁边的 `recalls N`) | SQLite: `SELECT COUNT(*) FROM recall_event, json_each(returned_ids) j WHERE j.value = ?` |
| **audit / restoration**(进程级灾难恢复) | file: `recall.jsonl`,SQLite 重建素材 |

所有 read path 走 SQLite(快),所有 write path 是 **file 先,SQLite 后**(详见下方 §写入路径)。

## Schema

### File 行格式(canonical · `recall.jsonl` 每行一个事件)

```json
{
  "event_id":   "01jzr5kq8h3f1d4w9m6p2x7c0a",
  "session_id": "sess-a1b2c3d4-f21fe60190b0",
  "source":     "claude-code",
  "location":   "/Users/zzz/.claude/projects",
  "ts":         "2026-05-31T06:42:01Z",
  "prompt":     "我想用 LanceDB 替换 Pinecone 怎么改",
  "top_k":      3,
  "returned": [
    {"card_id": "card_01jz8k2m", "insight": "选定 LanceDB 做向量存储"},
    {"card_id": "card_01jzp3nq", "insight": "异步数据库连接池实现"}
  ],
  "skipped": [
    {"card_id": "card_01jz9q3w", "insight": "搜索引擎核心原理"}
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `event_id` | string | 是 | ULID,无前缀(只在 recall 子系统内出现) |
| `session_id` | string | 是 | **canonical session_id**,详见 [§ session_id 怎么算](#session_id-怎么算) |
| `source` | string | 是 | hook 触发时声明的 adapter 名(`claude-code` / `codex` / ...)。冗余存方便 audit 时不用反推 |
| `location` | string | 是 | hook 触发时声明的 location 路径。同上,冗余存为了 audit 自包含 |
| `ts` | string | 自动 | UTC ISO 8601,`Z` 结尾 |
| `prompt` | string | 是 | 用户当次 hook 的输入文本,**原样保存**,不截断不归一化 |
| `top_k` | int | 是 | 本次 recall 用的 top_k 值(可能受 `--top-k` flag 或 settings 默认影响) |
| `returned` | array of `{card_id, insight}` | 是 | 本次新返回的卡 —— **每张卡带 insight 快照**,这样事后 card 被改/删,recall.jsonl 仍能还原"当时给用户看的是什么" |
| `skipped` | array of `{card_id, insight}` | 是 | 命中但因 dedup 被跳过的卡。同样带 insight 快照,排查"为啥这轮没新东西"时有用 |

### SQLite `recall_event` 行格式(derived index · 为查询速度)

```sql
CREATE TABLE recall_event (
  event_id      TEXT PRIMARY KEY,
  session_id    TEXT NOT NULL,
  prompt        TEXT NOT NULL,
  ts            TEXT NOT NULL,
  returned_ids  TEXT NOT NULL,           -- JSON array of card_ids only (no insight)
  skipped_ids   TEXT NOT NULL            -- JSON array of card_ids only
);
CREATE INDEX idx_recall_event_session_ts
  ON recall_event(session_id, ts DESC);
```

**SQLite 比 file 少**这些字段:
- `source` / `location` —— 查询时用不上(`recall list` 不按 source 过滤);要 audit 直接读 file
- `top_k` —— 同上,查询时用不上
- `returned[*].insight` / `skipped[*].insight` —— 现算更便宜:`recall read` 展示时 JOIN cards 表拿当前 insight;要历史快照走 file

**SQLite 比 file 多**:无。SQLite 是 file 字段的子集。

为什么不让 SQLite 等于 file?

- file 是"快照式 audit",字段越全越好(将来 card 被删了 file 仍有快照)
- SQLite 是"查询索引",字段越少越精炼(减少更新成本 / 索引大小)
- 两者各自服务一个目的,不强求字段一致

### 为什么 `returned` / `skipped` 在 file 里是 `[{card_id, insight}]` 而 SQLite 是 `[card_id]`

file 写的时候是同步事件:这一刻把 returned 的卡片完整快照写进去,**事件本身就是 immutable 的**。如果一年后 card_01jz8k2m 的 insight 被改写、甚至卡片被删,recall.jsonl 里的旧 event 仍说"当时返回的是 '选定 LanceDB 做向量存储'"。**这是 recall.jsonl 区别于 SQLite 的核心价值**。

SQLite 不存 insight 是为了避免冗余(insight 在 cards 表里有当前版本,join 即可)+ 避免 stale。`recall read` 展示时:
- 展示当前 insight → JOIN cards 表
- 展示历史 insight 快照(罕见需求) → 读 file 行

> JSON 数组列存成 TEXT,SQLite 自带 `json_each` / `json_array_length` 处理。**不**抽出成单独的 `recall_event_card` 关联表 —— 那会引入"主表 + 从表"两套写入,又掉回多 source-of-truth 的坑。一个事件对应一组卡的语义本来就是"原子整体",JSON 列正好对齐。

## session_id 怎么算

canonical session_id 的真实公式(由 `BaseAdapter.mint_session_id` 实现):

```
session_id = f"sess-{loc_code}-{tail}"

  loc_code = sha256(f"{source_name}#{location}").hexdigest()[:8]
  tail     = upstream_id.rsplit("-", 1)[1]    # UUID 最后一段
```

也就是说,算 canonical 要 **3 件输入**:`source_name` + `location` + `upstream_id`。

只有 `upstream_id`(平台原始 UUID)在 hook payload 里能拿到,**`source_name` 和 `location` hook 本身不知道** —— 它们属于"装这个 hook 的 host CLI 是谁、它的 session 文件在哪",这是 plugin install 时的知识。

所以 hook 命令必须**显式收**这两个 piece of info:

```bash
# Claude Code 装的 plugin 调:
memory.talk recall hook --source claude-code --location ~/.claude/projects

# Codex 装的 plugin 调:
memory.talk recall hook --source codex --location ~/.codex/sessions
```

(`--location` 可选,缺省走 adapter 的 `DEFAULT_LOCATION`,够覆盖单 endpoint 场景。多 endpoint 用户需要手动传。)

setup wizard 在实体化每个 host 的 plugin 时,把对应 `--source X` 写进 plugin 的 `hooks.json` 的 command 字符串 —— 不同 host 装的 plugin 拿到的 command 自然就不同。详见 [`../../cli/v3/recall.md#recall hook`](../../cli/v3/recall.md#memorytalk-recall-hook)。

### 为什么不靠 hook 服务端"猜" source

历史上 `util/ids.py:prefix_session_id` 干过这事 —— **写死 `ClaudeCodeAdapter` + `DEFAULT_LOCATION`** 然后调 `mint_session_id`。后果:

| Hook 来源 | recall 算出的 session_id | sessions 表里 sync 写的 session_id | 对得上? |
|---|---|---|---|
| Claude Code(默认位置) | `sess-{cc_loc}-{tail}` | 同 | ✅ |
| Claude Code(自定义位置) | `sess-{cc_DEFAULT_loc}-{tail}`(错) | `sess-{cc_actual_loc}-{tail}` | ❌ |
| **Codex** | `sess-{cc_loc}-{tail}`(完全错) | `sess-{codex_loc}-{tail}` | ❌ |

**0.8.x Codex 的 recall_log 跟 sync 后 sessions 表是完全两个 namespace,join 不上。** 这个 bug 一直没显形,因为旧设计也没有"join recall 跟 sessions"的视图 —— 直到现在 `recall list` / `recall read` 要按 session 聚合才暴露。

0.9.0 修这个 bug 的代价:`util/ids.py:prefix_session_id` 这个 legacy 函数从 recall 路径删除,recall 服务接 `(--source, --location, raw_uuid)` 三个参数,经 `BaseAdapter.mint_session_id` 算出 canonical。

### 不验证 session 在 sessions 表里存在

recall 是**实时** hook,sync 是**异步定时**。常见时序:

```
[hook 1]  POST /v3/recall {session_id: sess-<loc>-<tail>, prompt: ...}    ← 写 recall_event
[hook 2]  POST /v3/recall {session_id: sess-<loc>-<tail>, prompt: ...}    ← 写 recall_event
[hook 3]  POST /v3/recall {session_id: sess-<loc>-<tail>, prompt: ...}    ← 写 recall_event
[sync]    定时器跑 → 把这个 session 落到 sessions 表                       ← 现在才有 session 实体
```

写入路径 **不**查 sessions 表存在性,**不**加外键约束。等 sync 落地,recall_event 的 session_id 跟 sessions.session_id 同形,关联自然成立,不需 backfill。

## 路径布局

```
~/.memory.talk/
└── sessions/<source>/<sid[0:2]>/<sid>/
    ├── meta.json        ← sync 写
    ├── rounds.jsonl     ← sync 写
    ├── events.jsonl     ← sync / review / card 生命周期事件
    └── recall.jsonl     ← recall hook 每次追加一行(canonical)
```

`<sid[0:2]>` 是 canonical session_id 的前 2 个 charset 字符,沿用现有 sessions 目录分片约定。

**目录可能在 sync 之前就已经被 recall 创建**:hook 时算出 canonical session_id,如果 `sessions/<source>/<sid[0:2]>/<sid>/` 不存在,recall 服务**创建该目录**(mkdir -p)然后追加 `recall.jsonl`。`meta.json` / `rounds.jsonl` 留给 sync 后续来写,不冲突。

## 事件日志(`events.jsonl`)

**不**写入 `cards/{...}/events.jsonl`,也**不**写入 `sessions/<...>/events.jsonl`。recall 不是 card 或 session 的"生命周期事件" —— 它不改变 card 的内容、不改变 session 的 rounds,只是"在某个时刻命中了某张卡"。recall 自己有 `recall.jsonl` 作为完整记录。

(对比:Review 写 `card.events.jsonl` 的 `reviewed` 事件,因为 review 改 card stats。Recall 不改 session/card 的 payload。)

## 不存在的字段(以及为什么)

| 字段 | 为什么不要 |
|---|---|
| `card_stats.recall_count` | 旧设计有,**新设计 drop**。改成现算(SQLite `COUNT(*) ... json_each`)。换来 single source of truth |
| `recall_event.recall_id` (跟 review_id 命名一致) | 用 `event_id`,因为它是 event-shaped 而不是 entity-shaped(没有"读这一条 recall 内容"这种用法,只有"看时间线上发生了什么") |
| 单独的 `recall_event_card` 关联表 | 见上文 §Schema。会引入多表写入,违背 single source of truth |
| `card_id_set` 索引 | 现在不加。`json_each` 反向查"某卡被召了几次"在百卡量级是 ms 级,过早优化 |
| `recall_event.embedding_used` 等检索元数据 | recall 不可回放(embedding model / cards 都会变),没有意义记录 |

## 写入路径

只一个写入点:`memory.talk recall hook` 服务端处理。**顺序固定:先 file,后 SQLite**。

```python
# service/recall.py — pseudo-code
canonical_sid = adapter_for(source).mint_session_id(raw_uuid)
session_dir = data_root / "sessions" / source / canonical_sid[:2] / canonical_sid
session_dir.mkdir(parents=True, exist_ok=True)

event = {
    "event_id": new_ulid(),
    "session_id": canonical_sid,
    "source": source,
    "location": location,
    "ts": utc_now_iso(),
    "prompt": prompt,
    "top_k": top_k,
    "returned": [{"card_id": c.id, "insight": c.insight} for c in new_cards],
    "skipped":  [{"card_id": c.id, "insight": c.insight} for c in skipped_cards],
}

# 1. file first (canonical)
with open(session_dir / "recall.jsonl", "a", encoding="utf-8") as f:
    f.write(json.dumps(event, ensure_ascii=False) + "\n")

# 2. SQLite index next (best-effort)
try:
    await db.execute(
        "INSERT INTO recall_event "
        "(event_id, session_id, prompt, ts, returned_ids, skipped_ids) VALUES (?, ?, ?, ?, ?, ?)",
        (event["event_id"], canonical_sid, prompt, event["ts"],
         json.dumps([c["card_id"] for c in event["returned"]]),
         json.dumps([c["card_id"] for c in event["skipped"]]))
    )
    await db.commit()
except Exception as e:
    log.warning("recall_event SQLite insert failed; file is canonical, rebuild will recover: %s", e)
```

**为什么 file 必须先写**:file 是 canonical。SQLite 出问题时,future 的 rebuild 路径能从 file 完整恢复;file 出问题时,SQLite 里的索引没有上游可恢复(我们不会从 SQLite 反推 file)。

### 失败模式

| 阶段 | 失败 | 行为 |
|---|---|---|
| mkdir | 权限 / 磁盘 | 抛 → hook 服务端捕获 → 仍返回空 `hookSpecificOutput` JSON(契约:hook 永不 exit 非 0)→ 这次 recall **完全失败**,不去重不记账 |
| file 写 | 同上 | 同上 |
| SQLite 写 | 磁盘满 / SQLite 损坏 | log warning,**file 已经写了 → 这次仍算成功** →`recall hook` 仍返回正常 hookSpecificOutput → 用户看到正确的召回结果,只是 SQLite 这条索引行缺失。**SQLite drift 由 rebuild 路径修复(见下)** |

## SQLite 重建路径(0.9.0 范围外,合约写下)

**合约**:SQLite `recall_event` 表的内容**完全可以从 `recall.jsonl` 文件们重建**。任意时刻删 SQLite + 跑 rebuild → SQLite 内容应该跟 rebuild 前的 file 内容 1:1 对得上。

**实现暂缓**(0.9.0 不交):

- 真正发生 SQLite drift 是低频事件(磁盘满 / 损坏后恢复 / 跨机迁移)
- rebuild 本身是 ops 操作,不是日常 hook 路径
- 跟其它对象(cards / sessions)的 rebuild 命令应该用同一个入口(以后做 `memory.talk rebuild` 时一起加 recall 这一支)

合约先约定下来 + 写入路径按"file 先, SQLite 后, SQLite 失败可降级"的语义实现,留出未来 rebuild 的着力点。

## 读取路径

| 入口 | 查询形态 |
|---|---|
| `recall hook`(去重) | `SELECT DISTINCT j.value FROM recall_event, json_each(returned_ids) j WHERE session_id = ? AND j.value IN (...)` |
| `recall list` | `SELECT session_id, COUNT(*), MAX(ts), SUM(json_array_length(returned_ids)) FROM recall_event GROUP BY session_id ORDER BY MAX(ts) DESC LIMIT ?` |
| `recall read <session_id>` | `SELECT * FROM recall_event WHERE session_id = ? ORDER BY ts [DESC] LIMIT ?` |
| search/read response 里的 `recalls N` | 给一组 card_id,一次 IN 查询拿计数 |

**`recall_event` 不暴露独立 REST 资源** —— 没有 `GET /v3/recall-events/{id}`。它没有"作为对象被检索"的需求,只通过上面 4 个聚合视角访问。

## 跟其它对象的关系

```
RecallEvent
  │
  ├── session_id ──────► Session(可能还没 sync 进 v2,见下)
  │
  ├── returned_ids[] ──► Card(本次新返回的)
  │
  └── skipped_ids[]  ──► Card(命中但被去重的)
```

跟 [Card](talk-card.md) 的关系是**单向引用**:RecallEvent 提到 card_id,但 card 本身**不存反向链** —— card 是否被 recall 过、被 recall 几次,**始终现算**(`COUNT(*) ... FROM recall_event WHERE j.value = card_id`)。

跟 [Session](session.md) 同理:RecallEvent 提到 session_id,但 session 不知道自己产生过 RecallEvent。

(跟 sync 的时序详见上方 [§ session_id 怎么算 / 不验证 session 在 sessions 表里存在](#不验证-session-在-sessions-表里存在))

## 迁移(0.8.x → 0.9.0)

0.9.0 一次性修三件事:

1. **schema 改单 source-of-truth(file canonical)**
   - `DROP TABLE recall_log` —— 不迁移历史。旧表注释 "in-memory-ish — cleared on rebuild",且没存 prompt 也补不出 RecallEvent
   - `ALTER TABLE card_stats DROP COLUMN recall_count` —— 改 derived,旧值丢
   - `CREATE TABLE recall_event ...` + 新索引(SQLite,新派生索引)
   - **新增 `sessions/<source>/<sid[0:2]>/<sid>/recall.jsonl` 写入路径**(canonical · 每次 recall 追加一行)

2. **修 Codex/多 endpoint session_id bug**
   - 删 `util/ids.py:prefix_session_id` 这个 legacy 函数(它写死 claude-code 适配器)
   - recall 服务改接 `(--source, --location, raw_uuid)` 三参数,经 `BaseAdapter.mint_session_id` 算 canonical
   - 各 host 的 plugin asset 里 `hooks.json` 命令字符串改成 `memory.talk recall hook --source <X> [--location <Y>]`(详见 [`../../cli/v3/recall.md`](../../cli/v3/recall.md))
   - **副作用:0.8.x Codex 用户的 recall_log 历史在 schema 改完之后即使被人为留下也无意义(用的是错的 session_id namespace)**,直接随旧表 DROP 一并清掉

3. **写入路径调整**:hook 服务端的"先 file 后 SQLite"两步写入(详见上方 §写入路径)。SQLite 写失败可降级(file 已是 canonical)

升级路径写在 release notes:**recall 历史会清零**(包括 card 的 `recalls N` 数字)。0.8.x Codex 用户额外得知"以前算错了,现在从 0 重新累计"。语义上跟"从 0 开始记账"等价,用户能理解。

升级后用户需 **`memory.talk setup` re-run 一次**让 hook step 重新实体化 plugin assets,确保新的 `--source ...` 命令字符串被写进 host 的 plugin 里。setup wizard 在 hooks step 检测到 plugin assets 漂移会自动 re-materialize + re-install(已是 0.8.6 既有行为)。

## 不变量(invariants)

1. **file 是 canonical**;SQLite `recall_event` 是 derived index。两者 drift 时以 file 为准,合约上 SQLite 可从 file rebuild(实现暂缓)
2. `recall.jsonl` **append-only**:从不 UPDATE / DELETE(除非显式 rebuild)
3. `recall_event` SQLite 表理论上也是 append-only,但**允许 drift**(写失败 / 跨机迁移),rebuild 时按 file 校对
4. 同 `(session_id, card_id)` 在所有 RecallEvent 的 `returned` 里**最多出现一次** —— 由 dedup 路径保证(已在 returned 里的下次进 skipped)。**不**靠数据库约束强制,因为约束跨 JSON 列没有合适表达
5. 一个 RecallEvent 的 `returned` 和 `skipped` **不相交**(同一张卡不会同时是 "本次新返回" 和 "本次去重")
6. `prompt` 永远非空字符串(空 prompt 在写入路径就会被拒掉)
7. **写入顺序固定**:mkdir → write recall.jsonl → INSERT recall_event。SQLite 失败不回滚 file(file 是 canonical,符合"宁可前进不可回退"的契约)

## 容量预期

- 一个用户每天写约 100 次 hook(假设积极使用)→ 100 行/天 → ≈ 36k 行/年
- 每行 ~ 200 bytes(prompt 中位数 + 2-3 张卡 ID)→ 7 MB/年
- SQLite + B-tree 索引在 10 万行下查询仍是 ms 级

**不需要分区 / 不需要冷归档**。如果未来真的有几百 GB 量级,加一个 `purge_before(ts)` ops 命令即可,本设计不预留这个能力。
