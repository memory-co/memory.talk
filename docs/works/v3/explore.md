# explore — 先验/后验抽卡工作区（设计）

一个 **explore** 是一个**抽卡工作区**：绑定一个或多个「焦点会话」，把相关 session 按时间分成**先验(prior)**（焦点及以前——抽卡的素材）和**后验(posterior)**（焦点以后——验卡的证据），给你一个**充分、可靠、含先验/后验的探索上下文结构**，让你（或 LLM）在里面清晰地抽 card、再用后验 review 它。

> **状态：设计提案，未实施。**
>
> **它取代旧的 explore（旧的不迁移）。** 项目现在的 `explore` 是一个**全局** cwd 命名空间（`settings.explore.cwd`）——你在那个目录里跑 Claude Code 抽卡/写 review，期间 recall hook 被压制（见 [explore-cwd-suppression.md](explore-cwd-suppression.md)）。这个功能基本没被用起来，**旧数据/feed 不迁移**。但它那个核心机制——**靠 `session.metadata.cwd` 物理信号认 session + 在工作区里压制 recall**——被**复用**：新设计从"一个全局 explore 目录"改成"**每个 explore 各自一个目录**"。「抽卡工作区」这个本意不变，命名冲突靠**合并**消解（不改名）。

相关:
- 旧 explore（cwd 召回压制，本设计取代它）: [explore-cwd-suppression.md](explore-cwd-suppression.md)
- Card 创建流程(rounds 引用展开 + source_cards DAG): [card-creation-flow.md](card-creation-flow.md)
- Review 怎么影响 card stats(stance + 沉浮): [review-impact.md](review-impact.md)
- Session rounds 写入(append-only + round 时间戳): [session-rounds-write.md](session-rounds-write.md)
- File-canonical 模式(card/review/session 共用): [file-canonical-pattern.md](file-canonical-pattern.md)

## 核心定性：explore 是「君子协定」，不是硬门

explore **只负责把先验/后验划分清楚**，提供给你当上下文——它**不强制**「抽卡只能引先验、review 只能用后验」。违反约定不会被服务端拒绝。

这是个有意的选择：抽卡是 LLM/人在工作区里做的判断活，explore 的价值是**把"线"画清楚、把两堆 session 摆明白**，让判断有一个可靠的时间结构可依——而不是当个会拒绝写入的栅栏。（对比：早先草案设计成硬执行防火墙，经评估改成君子协定。）

**为什么先验/后验这个划分有价值**：它把「这条洞见后来站住脚了吗」变成一个干净的时间实验——card 从分割线**之前**的素材蒸馏，再用**之后**发生的事去检验。约定上抽卡和验卡在时间上不重叠，于是后验的 +1/−1 才是**留出样本**的确认/否定（而不是"用抽卡的那些 round 自我确认"）。explore 把这个结构摆好；honor 它是君子之约。

## 时间：全程带时区 UTC

所有时间一律**带时区的 UTC**，比较前先解析、存储统一 canonical UTC-Z。`round.timestamp` 是各平台原样透传的异构字符串（毫秒/秒精度、可能带 `+08:00`），**字典序 ≠ 时间序**，所以绝不直接比字符串：

```python
def parse_instant(s):                      # 复用 service/search.py / cli/_format.py 的写法
    try: dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError): return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)   # 裸时间按 UTC
def canonical_z(dt):
    return dt.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
```

### session 增加 `last_round_update_time`（派生、实时）

每个 session 加一个派生字段 `last_round_update_time`（canonical UTC-Z）：**append 新 round 时更新成最新的 round 时间**。

```
append_rounds 时:
  last_round_update_time = canonical_z(max(
      parse_instant(本次新 round 的所有 timestamp),
      parse_instant(原 last_round_update_time),
  ))
  # 若该 session 从来没有任何可解析的 round 时间戳 → 兜底 created_at，再兜底 synced_at
```

先验/后验就按这个字段**实时**算（session 长出新 round → 它的时间前移 → 分区可能随之变化）。因为 explore 是君子协定、没有"冻结正确性"要保护，实时反而更简单、也更贴合"工作区是活的"。

> 注：旧设计纠结的"冻结快照 vs 实时重算"在君子协定下不再是问题——没有不可纠正的硬门会因为分区漂移而出错。

## 模型：每个 explore 一个目录，按路径圈关联会话

- **每个 explore 建一个自己的目录**（`<explore_root>/<explore_id>/` 或用户指定路径）。你在这个目录下跑 Claude Code 干活。
- **关联会话集按路径活算**：凡 `session.metadata.cwd` 落在该 explore 目录前缀下的 session，就是这个 explore 的关联会话（复用旧 explore 的 cwd 物理信号，前缀匹配）。这是 **live 的**——目录下后续新跑的 session 自动进来（在"这个目录"这个范围内），不需要创建时冻结捕获；目录之外的 session 永不进来。
- **焦点会话(focus) / 分割线 divider**：在关联集里选 1+ 个 session 当焦点，`divider = 焦点们 last_round_update_time 的最大值`（你工作的"现在"）。
- **先验/后验划分**（在该目录的关联集内，实时按 `last_round_update_time` 算）：
  - `prior = {关联 session : last_round_update_time <= divider}`（**含焦点**——抽卡的素材）
  - `posterior = {关联 session : last_round_update_time > divider}`

> 单焦点时退化成你最初说的「这个 session 含及以前 = 先验」。一个 explore 目录 = 一条按时间排开的 session 流，focus 把它切成"用来抽卡的先验"和"用来验卡的后验"。
>
> ⚠️ **一处待你确认**：先验是否就是「本目录里更早的 session」（自包含），还是先验应来自目录之外的全局历史、本目录只是跑抽卡会话的工作区？文档暂按**自包含**写（见[待定](#仍待定)）。

## card / review 怎么挂到 explore（关联，非强制）

- `cards.explore_id` / `reviews.explore_id`（可空列，NULL=freeform）：在某个 explore 工作区里抽的卡 / 写的 review 盖上它的戳。**只是关联标记，不触发任何拒绝逻辑。**
- 约定（君子，不强制）：在 explore 里抽卡**应当**只引先验 session 的 round；review **应当**用后验 session。explore 的视图把"先验/后验"摆清楚来**支持**这个约定，但不阻止你违反。
- 复用现有写路径：`CreateCardRequest` / `CreateReviewRequest` 加可选 `explore_id`，带了就盖戳 + 往 explore 的 `events.jsonl` 记一条；其余（文件镜像/事件/stats/向量）全不变。

## 视图：先验/后验 + 验证进度

explore 的核心产出是一个**清晰的上下文 + 进度视图**：

- **先验堆 / 后验堆**：两列 session，低置信时间（兜底 ingest 时钟）标 `~`。
- **后验用过没**：每个后验 session 标 `spent`（在本 explore 下被用作 review ≥1 次）—— 叫 **spent**（花过了），不叫 "validated"。`unspent` = 还没用过的后验 session，单列出来（「你还能用这些后验去验」）。
- **每张卡的判定**（explore 局部，以 card 为主表 LEFT JOIN 本 explore 的 review）：
  ```
  untested  : 没有后验 review            ← 工厂最该看的：还没验的库存
  confirmed : up > down 且 up > 0
  refuted   : down > up
  contested : up == down 且 up > 0
  neutral   : 只有 0 分 review
  ```
  一个后验 session 对同一张卡可能先 +1 后 −1（append-only 改主意）→ 按 `(session_id, card_id)` 取**最后一次** stance、按 distinct session 计票。
- **局部 vs 全局**：explore 计票只数 `reviews WHERE explore_id`；全局 `card_stats` 仍聚合所有 review（沉浮信号不分区）。视图把两者并排标清楚：`本 explore: +2/−0 · 终身: +2/−5`。

## 对象模型 + 存储

**版本**：新表 + 加列 = minor bump（schema 变更）。

```sql
CREATE TABLE explores (
  explore_id        TEXT PRIMARY KEY,    -- explore_<ulid>
  dir_path          TEXT NOT NULL,       -- 该 explore 的目录（关联集的权威依据，前缀匹配 cwd）
  focus_session_ids TEXT NOT NULL,       -- JSON 数组：选中的焦点会话
  divider_at        TEXT NOT NULL,       -- 焦点 last_round_update_time 的最大值，canonical UTC-Z
  created_at        TEXT NOT NULL,
  note              TEXT
);
ALTER TABLE sessions ADD COLUMN last_round_update_time TEXT;  -- 派生、append 时更新
ALTER TABLE cards    ADD COLUMN explore_id TEXT;              -- NULL = freeform
ALTER TABLE reviews  ADD COLUMN explore_id TEXT;              -- NULL = freeform
```

- **关联集的权威依据是 `dir_path`**（按 `metadata.cwd` 前缀活算），不是一份冻结的 id 列表——目录下的 session 是动态的。需要列表时按 `dir_path` 查 / 缓存即可（满足"存关联 session"的诉求，但路径才是源头）。
- 先验/后验也**不**冻——是关联集 + 各 session 当前 `last_round_update_time` 的实时函数。

文件镜像 + 事件（house style，explore 的目录本身就是它的工作区）：
```
<dir_path>/                              ← 工作区目录；这里跑的 claude session 即关联会话
explores/<bucket>/<explore_id>/explore.json   ← manifest（dir_path + focus + divider）
explores/<bucket>/<explore_id>/events.jsonl   ← created / card_minted / review_filed
```

## API / CLI 面

- **新对象端点**用复数 `/v3/explores`（和旧 `/v3/explore` cwd-feed 区分；旧 feed 由本设计取代，迁移见待定）：
  - `POST /v3/explores {focus_session_ids[], note?}` → 创建：捕获关联集、算 divider、写库+文件。
  - `GET /v3/explores/{eid}` → manifest + 先验/后验堆 + spent/unspent + 每卡 status（实时算）。
  - `GET /v3/explores?limit=` → 列表。
- **抽卡/验卡复用现有端点**：`card create --explore <eid>` / `review create --explore <eid>` 注入 `explore_id`。一条抽卡路径、一条验卡路径。
- **CLI** `cli/explore.py`：`explore create <focus...> [--note]` / `explore view <eid>` / `explore list`。

## 与旧 explore / recall / DAG / searchbase 关系

- **旧 explore（cwd 召回压制）**：本设计取代它，**旧数据/feed 不迁移**（基本没被用起来）。复用的是它的两个机制：① 按 `session.metadata.cwd` 前缀认 session（现在 per-explore 目录）；② 在 explore 目录里跑 claude 时**压制 recall**（抽卡时让 LLM 清醒地自己决定看什么）。`settings.explore.cwd`（旧的单一全局目录）可废弃或留作 `<explore_root>` 的默认根。
- **recall**：卡上的 `explore_id` 是惰性元数据，recall 不必读。（可选未来：「只 recall 某 explore 的卡」。）
- **血缘 DAG**：结构不变；`explore_id` 只是 tag，不加边、无环险。君子协定下也不对 `source_cards` 做时间强制。
- **searchbase**：零新增。卡只 embed insight；explore 按 id 查、不做语义检索。`explore_id` 纯活在 SQLite + JSON 镜像。

## 仍待定

1. **先验的来源**（最关键）：先验 = 「本 explore 目录里更早的 session」（自包含，文档现按此写），还是先验应来自**目录之外的全局历史**、本目录只是跑抽卡会话的工作区？这决定整个数据流。
2. **多焦点会话的 divider 语义**：当前定为「焦点们 `last_round_update_time` 的最大值，焦点整体归先验侧」。确认；还是想让焦点单独一档（既非先验也非后验）？
3. **`last_round_update_time` 回填**：给存量 session 怎么算（migration 里遍历 rounds.jsonl 一次性回填，还是懒加载）。

> 已定（本轮）：旧 explore **不迁移**；关联集**按路径**（per-explore 目录，cwd 前缀活算）；时间全 UTC；君子协定不强制。
