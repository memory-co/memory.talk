# explore — 先验/后验抽卡工作区（设计）

一个 **explore** 是一个**抽卡工作区**：你在它的目录里跑 Claude Code 来驱动分析，给一条**分割线**（填一个全局入口会话、或直接给一个时间，最终都化成一个冻结的 `divider_at`），它就把**全局 session 池**切成**先验(prior)**（线及以前——抽卡素材）和**后验(posterior)**（线以后——验卡证据），给你一个**充分、可靠、含先验/后验的探索上下文结构**。注意：explore 自己目录里那些"驱动分析"的 session，**被排除**在先验/后验之外（实验记录本 ≠ 被分析的数据）。

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

**存量回填**：加这列时，在 migration 里**遍历一遍每个 session 的 `rounds.jsonl`** 把 `last_round_update_time` 一次性算出来写好（按上面同一套解析/兜底规则）；之后只在 append 时增量更新。

> 注：旧设计纠结的"冻结快照 vs 实时重算"在君子协定下不再是问题——没有不可纠正的硬门会因为分区漂移而出错。

## 模型：两层 session，分得很清楚

explore 涉及**两类完全不同的 session**，关键是别混：

| | 是什么 | 在分析里的角色 |
|---|---|---|
| **驱动 session**（explore 自己的） | 你在 explore 目录里跑 Claude Code 做抽卡推理的会话——「实验记录本」 | **被排除**，不是被分析的对象 |
| **被分析 session**（全局） | 全局 session 池里你真实的工作会话 | 按 `divider_at` 切成**先验 / 后验** |

- **每个 explore 建一个自己的目录**（`explores/<YYYY>/<MM>/<explore_id>/`，一个**自由工作区**，系统只放一个 `explore.json`，见[存储](#对象模型--存储)）。你在这目录下跑 claude 驱动分析；凡 `session.metadata.cwd` 落在此目录前缀下的 session = 这个 explore 的**驱动 session**（复用旧 explore 的 cwd 物理信号）。
- **分割线的来源有两种，最终都化成一个时间 `divider_at`**：
  - 填一个全局**入口会话** `entrypoint_session_id` → 读它**创建那一刻**的 `last_round_update_time`；
  - 或直接给一个**时间**。
- **`divider_at` 在创建时冻结**。传入口会话时只是借它当时的时间算出这条线——**即使这个会话之后又更新，也不动已划定的边界**。
- **先验 / 后验 = 全局 session 池**，按 `divider_at` 切，**再减去本 explore 的驱动 session**：
  - `prior     = {全局 s ：s ∉ 驱动集 且 last_round_update_time(s) <= divider_at}`（创建时入口会话正好在线上 → 先验）
  - `posterior = {全局 s ：s ∉ 驱动集 且 last_round_update_time(s) >  divider_at}`

> 为什么排除驱动 session：你在 explore 里"讨论怎么抽卡"的那些会话，如果也算进先验/后验证据，就污染了实验——把实验记录本从数据里剔掉，先验/后验才干净。
>
> **线冻结、归属实时**：`divider_at` 创建时定死；其余全局 session 按它们**当前**的 `last_round_update_time` 相对这条冻结线实时归到先验/后验（一个先验 session 后续长出更晚的 round，可能漂到后验侧——君子协定下无妨，不存冻结分区）。

## card / review 怎么挂到 explore（关联，非强制）

- `cards.explore_id` / `reviews.explore_id`（可空列，NULL=freeform）：在某个 explore 工作区里抽的卡 / 写的 review 盖上它的戳。**只是关联标记，不触发任何拒绝逻辑。**
- 约定（君子，不强制）：在 explore 里抽卡**应当**只引先验 session 的 round；review **应当**用后验 session。explore 的视图把"先验/后验"摆清楚来**支持**这个约定，但不阻止你违反。
- 复用现有写路径：`CreateCardRequest` / `CreateReviewRequest` 加可选 `explore_id`，带了就盖个戳；其余（card/review 各自的文件镜像、事件、stats、向量）全不变。explore 不另起 events.jsonl——"这个 explore 抽了哪些卡 / 收了哪些 review"从 SQLite `WHERE explore_id` 查即可。

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

explore 的目录是一个**自由的工作区**——Claude Code 在里面跑、想写什么写什么，**不是元信息目录**。所以系统**绝不**往里强加结构化 jsonl 让 AI 维护（events / index / per-session reviews 这些一律不要）：AI 不会可靠遵守 schema，工作区会乱成一团。

**memory.talk 对这个目录的纪律是「写一次、之后只读」**：
- 创建那一刻写**一个** `explore.json`，**此后再也不写**（连这份也不更新）——目录完全交给 AI 自由用。
- 但 memory.talk **会读**这个目录：把 AI 的产出/进展展示给人看（`explore view`）。
- 权威记录在 SQLite 的 `explores` 行；`explore.json` 只是创建时一次性丢进去的**人读镜像**。

```
explores/<YYYY>/<MM>/<explore_id>/      ← 工作区目录（claude 在此跑 = 驱动集，cwd 落此前缀即排除）
  explore.json                          ← 创建时写一次，此后系统不再碰：divider_at + entrypoint + dir_path
  …                                     ← 其余全是 claude 自由产出的工作文件，系统只读不写
```

> 按创建年/月分目录（`<YYYY>/<MM>/`，不用 session/card 那种 `<source>/<hash-bucket>`）：explore 无平台归属、量不大，年月排开翻着顺眼。

**card / review 不落在工作区**，走正常路径进各自现成的 canonical 罐：
- **card** 是把**多个先验 session** 综合出的洞见 → 属于 explore（工厂产出），但卡本体仍存全局 `cards/`（card-creation-flow 那套），只在 SQLite 上盖个 `explore_id` 瘦戳标记"这是哪个 explore 抽的"。**不挂到任何单个 session 下。**
- **review** = `(后验 session, card, stance)` → 存全局 `reviews/` + `explore_id` 戳。
- 抽卡/验卡靠 `card create --explore <eid>` / `review create --explore <eid>`，由 **CardService/ReviewService 可靠写**——不是指望 AI 往工作区 dump 文件。

> 所以"细节不进 SQLite"靠的是 **card/review 本来就 file-canonical**（各自的罐 + 瘦 SQLite 索引），explore 只加一个 `explore_id` 戳。视图（先验/后验堆、spent/unspent、每卡判定）全部从 SQLite `cards/reviews WHERE explore_id` 实时算，工作区里不需要任何索引文件。

**SQLite 瘦索引**（新表 + 加列 = minor bump）：

```sql
CREATE TABLE explores (
  explore_id            TEXT PRIMARY KEY, -- explore_<ulid>
  dir_path              TEXT NOT NULL,    -- = explores/<YYYY>/<MM>/<explore_id>/；cwd 落此前缀的 session = 驱动集(排除)
  divider_at            TEXT NOT NULL,    -- 冻结的分割线时间，canonical UTC-Z（本质参数）
  entrypoint_session_id TEXT,             -- 可空：用入口会话创建则记下(仅 provenance)；直接给时间则 NULL
  created_at            TEXT NOT NULL,
  note                  TEXT
);
ALTER TABLE sessions ADD COLUMN last_round_update_time TEXT;  -- 派生、append 时更新
ALTER TABLE cards    ADD COLUMN explore_id TEXT;              -- NULL = freeform
ALTER TABLE reviews  ADD COLUMN explore_id TEXT;              -- NULL = freeform
```

- **驱动集**的权威依据是 `dir_path`（按 `session.metadata.cwd` 前缀活算）。
- 先验/后验**不**冻、也不存——是「全局 session 池 − 驱动集」按各 session 当前 `last_round_update_time` 相对 `divider_at` 的实时函数。
- card/review 仍是 SQLite 核心对象（沉浮/检索要用），但它们在**某 explore 下的明细**进 `sessions/<session_id>/` 文件；`explore_id` 列只是个瘦关联戳。

## API / CLI 面

- **新对象端点**用复数 `/v3/explores`（旧 `/v3/explore` cwd-feed 由本设计取代、不迁移）：
  - `POST /v3/explores {entrypoint_session_id? | divider_at?, note?}` → 二选一定分割线；创建工作区目录、冻结 `divider_at`、写库+文件。
  - `GET /v3/explores/{eid}` → manifest + 先验/后验堆 + spent/unspent + 每卡 status（实时算）。
  - `GET /v3/explores?limit=` → 列表。
- **抽卡/验卡复用现有端点**：`card create --explore <eid>` / `review create --explore <eid>` 注入 `explore_id`。一条抽卡路径、一条验卡路径。
- **CLI** `cli/explore.py`：`explore create (<entrypoint_session_id> | --at <time>) [--note]` / `explore view <eid>` / `explore list`。

## 与旧 explore / recall / DAG / searchbase 关系

- **旧 explore（cwd 召回压制）**：本设计取代它，**旧数据/feed 不迁移**（基本没被用起来）。复用的是它的两个机制：① 按 `session.metadata.cwd` 前缀认 session（现在 per-explore 目录）；② 在 explore 目录里跑 claude 时**压制 recall**（抽卡时让 LLM 清醒地自己决定看什么）。`settings.explore.cwd`（旧的单一全局目录）可废弃或留作 `explores/` 根的默认位置。
- **recall**：卡上的 `explore_id` 是惰性元数据，recall 不必读。（可选未来：「只 recall 某 explore 的卡」。）
- **血缘 DAG**：结构不变；`explore_id` 只是 tag，不加边、无环险。君子协定下也不对 `source_cards` 做时间强制。
- **searchbase**：零新增。卡只 embed insight；explore 按 id 查、不做语义检索。`explore_id` 纯活在 SQLite + JSON 镜像。

## 设计已全部敲定

- **分割线** = 一个**冻结的 `divider_at`**：入口会话**或**直接给时间，二选一；入口会话只取它创建那刻的 `last_round_update_time`，之后更新不动线。
- **先验/后验** = **全局 session 池**按 `divider_at` 切、**减去 explore 目录的驱动 session**；归属实时（线冻、归属活）。
- **驱动集** = `metadata.cwd` 落在 explore 目录前缀下的 session（被排除）；**`metadata.cwd` 缺失 → 当作非驱动，仍参与先验/后验分析**。
- **`last_round_update_time`** 存量在 **migration 里遍历 rounds.jsonl 一次性回填**、之后 append 增量更新；全程带时区 UTC。
- **存储**：explore 目录是**自由工作区**（claude 在此跑），系统只放一个 `explore.json`，**不往里塞结构化 jsonl**；card/review 走正常 API 进各自现成的全局罐 + `explore_id` 瘦戳；视图从 SQLite `WHERE explore_id` 算。
- **旧 explore 不迁移**（复用其 cwd 信号 + recall 压制，改成 per-explore 目录）。
- **君子协定**：explore 只摆清先验/后验结构，**不强制**抽卡/review 的引用约束。
