# explore — 先验/后验抽卡工厂（设计）

一个 **explore** 是一个**冻结的抽卡工厂快照**：选一个 session 当「分割线」，把创建时可见的所有 session 切成**先验(prior)**（分割线及以前）和**后验(posterior)**（分割线以后）；card 只许引用先验证据抽出来，再只许用后验证据去 review（支持 +1 / 否定 −1）验证它。

> **状态：设计提案，未实施。** 本文是经一轮多智能体对抗审查（23 个确认问题，含 2 个 blocker）收敛后的设计。
>
> ⚠️ **命名冲突**：项目里 `explore` 这个词**已经被占用**——指 hook 的 cwd-namespaced agent workspace 模式（见 [explore-cwd-suppression.md](explore-cwd-suppression.md)，recall 里的 `test_hook_explore_skip`）。本文这个「抽卡工厂」是**另一个东西**，和那个不共享任何数据。落地前要么改名（Retro / Snapshot / Lens），要么靠路由前缀区分（`/v3/explores` 对象 vs `/v3/explore/*` feed）。见[§9 待定](#9-仍待定)。

相关:
- Card 创建流程(rounds 引用展开 + source_cards DAG): [card-creation-flow.md](card-creation-flow.md)
- Review 怎么影响 card stats(stance + 沉浮): [review-impact.md](review-impact.md)
- Session rounds 写入(append-only + round 时间戳): [session-rounds-write.md](session-rounds-write.md)
- File-canonical 模式(card/review/session 共用，explore 也照此): [file-canonical-pattern.md](file-canonical-pattern.md)

## 动机：为什么「先验→后验防火墙」有价值

它把「这条洞见后来站住脚了吗？」变成一个**干净、可审计的时间实验**：card 是从分割线**之前**你已知的东西里蒸馏出来的假设；review 用分割线**之后**发生的事去检验它。

没有这道防火墙，证据和验证会互相泄漏——你会用「当初抽出这张卡的那些 round」去「确认」这张卡，结果不可证伪。防火墙强制**抽卡和验卡在时间上严格不重叠**，于是一个 explore 下的 +1/−1 才真正意味着**留出样本(out-of-sample)的确认/否定**——这正是「回顾」唯一想要的信号。

（这本质上是机器学习的 train/test split：先验=训练集，后验=留出集，分割线防止数据泄漏。）

## 三个时间概念（核心，先讲清楚）

explore 涉及**两条正交的时间轴**，加上一个比较基准，最容易混，先单列：

| 概念 | 回答什么 | 用哪个时间 |
|---|---|---|
| **可见性天花板 ceiling** | 这个 session 在工厂开张时存在吗？ | `session.synced_at`（服务器 ingest 时钟） |
| **先验/后验分割** | 这个 session 在分割线之前还是之后？ | `session.last_at`（对话时钟，见下） |
| **分割线 divider_at** | 线划在哪 | 锚点 session 的 `last_at` |

### 时间戳必须解析后比较，绝不能比字符串（blocker）

`round.timestamp` 是各 adapter **原样透传**的平台字符串（`adapters/claude_code.py`、`codex.py` 零规范化），所以是**异构**的：Claude Code 是毫秒精度 `…56.789Z`，服务器自己的 `_utc_iso()` 是秒精度 `…56Z`，codex 可能带 `+08:00` 偏移。

**字典序 ≠ 时间序**：
- `'…56.789Z' < '…56Z'`（`.`=0x2E 排在 `Z`=0x5A 前）——毫秒串字典序更小，但时间更晚 → `max()` 取错「最后一条」；
- `'…20:00:00+08:00'`（=12:00 UTC）字典序 > `'…13:00:00Z'`（=13:00 UTC），但时间更早。

防火墙是 append-only、不可纠正的硬门，错分一次就**永久**错。所以**必须先解析成带时区的 datetime 再比**（复用代码库已有写法 `service/search.py` / `cli/_format.py`），存的时候统一回**秒精度 `Z`**：

```python
def parse_instant(s):
    try: dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError): return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)

def canonical_z(dt):
    return dt.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
```

### `last_at`：session 的「最后一条记录时间」+ None 兜底

```python
def compute_session_last_at(session_row, rounds) -> (iso_z, confidence):
    insts = [parse_instant(r["timestamp"]) for r in rounds if r.get("timestamp")]
    insts = [d for d in insts if d]
    if insts:
        return canonical_z(max(insts)), "rounds"          # 主：最晚的真实 round 时间
    floor = session_row["created_at"] or session_row["synced_at"]
    return canonical_z(parse_instant(floor) or parse_instant(session_row["synced_at"])), "ingest"
```

- **主基准** = 解析后 round 时间戳的**时间最大值**（不是字符串 max）。
- **None 兜底** = 先 `created_at`（平台对话**开始**时间，是「事情何时发生」的近似），再 `synced_at`（ingest 时刻，最后兜底）。**不要**无脑跟 `synced_at` 取 max——否则一个很老的 session 在 explore 前刚被批量 sync，会被错拽进后验。
- **置信标记** `ts_confidence ∈ {rounds, ingest}`：走了兜底的标 `ingest`，视图里用低置信标记（`~`）渲染——**降级可见，绝不静默**。

### ceiling 用 `synced_at`，不用 `created_at`（blocker）

候选宇宙 = `synced_at <= ceiling_at`（`ceiling_at == created_at == T_explore`）。

**为什么不用 `created_at`**：它 schema 默认是**空字符串**，codex adapter 遇到截断/损坏文件会写 `''`，而 `'' <= T_explore` 字典序恒真 → 空 `created_at` 的 session 会永远漏进来。`synced_at` 是服务器设的、`NOT NULL`、秒精度 UTC-Z、每次 append 都刷新——「explore 开张后才第一次 sync ⇒ 永不可见」才成立且防篡改。

## 先验/后验/边界——冻结算法

- **A. ceiling**：取 `synced_at <= T_explore` 的 session 当候选。
- **B. divider**：`divider_at = compute_session_last_at(锚点)`，存进 `explores.divider_at`，**永久冻结**——锚点之后再 append 不挪这条线（明确写死，消除「锚点一直在长」的歧义）。锚点本身归**先验**（你说的「含这个 session」）。
- **C. 整 session 归桶**（严格 / 锚点除外才包含）：
  - `prior = {锚点} ∪ {s≠锚点 : last_at(s) < divider_at}`
  - `posterior = {s≠锚点 : last_at(s) > divider_at}`
  - `boundary = {s≠锚点 : last_at(s) == divider_at}` → **单独一桶**

  和分割线**正好相等**的非锚点 session 是「同时」不是「更早」，不能靠 ULID 顺序硬塞进先验（会削弱防火墙）。`boundary` 既不能抽卡也不能 review，但**显式列出**让人看到。

### 冻结快照是唯一权威（消除双真相源 blocker）

> **`explore.json.partition`（冻结的先验/后验/边界三张表）是成员归属的唯一权威。** 防火墙、validated 视图、所有渲染都读这张冻结表，**对已创建的 explore 不做任何实时 `last_at` 重算**。

为什么必须这样：session 是 append-only，`last_at` 会随新 round 增长。如果还留一条「实时 SQL 重算」路径，那么——先验 session S 被一张卡引用为证据后、explore 之后 S 又追加了晚时间戳的 round → 实时重算把 S 判成后验，和冻结表矛盾，也和「已经有卡合法引用 S 当先验」矛盾。所以实时重算**直接砍掉**。（若为性能加 `sessions.last_at` 派生列，那是给别的 feed 用的**当前值**，**显式不**参与 explore 成员判断。）

快照不仅冻结「谁是先验/后验」，还冻结**每个先验 session 当时有几条 round**（`round_count_at_snapshot`）——这关系到 round 粒度防火墙，见下。

## 防火墙——在哪强制

两道门都在 **service 层服务端**（CLI 只是 HTTP 瘦客户端，不是信任边界），**仅当请求带 `explore_id` 时**才启动（不带 = 今天的 freeform 行为，原样不动）。成员判断是**对冻结表的 O(1) 集合查**，不重算时间。

### 抽卡门（`CardService.create`，带 `explore_id` 时）

1. **先验证据非空**：`rounds` 引用的 session 不能为空。否则拒（`∀ over empty == true` 的坑——零证据卡会蒙混过关并被盖戳）。explore 下**不允许**纯合成卡（rounds=[] 只靠 source_cards），那违背工厂「基于先验」的前提（freeform 仍允许）。
2. **每条引用的 round 都在先验、且在快照内**：对每个 `(session_id, indexes)`——
   - `session_id ∈ partition.prior`，且
   - 每个 `index <= round_count_at_snapshot[session_id]`。

   第二条堵住「先验 session（含锚点）后来又长出新 round，卡却引用了这条未来 round 当先验证据」的泄漏——**只能引用 T_explore 当时已存在的 round**。这让防火墙是 **round 粒度**的，贴合你「引用必须基于先验」的原话。
3. **`source_cards` 的时间契约**（消除传递性泄漏 blocker）：
   - `derives_from Y`：要求 `Y.explore_id == 本 explore` **或** `Y.rounds` 的每个 session 都在本 explore 的先验里（即 Y 自己也是先验接地的）。否则拒——`derives_from` 意味着「从 Y 蒸馏」，血缘必须传递性地先验。
   - `supersedes`：explore 下**禁止**（400）。冻结的先验快照不该去「推翻替换」一张证据可能晚于快照的卡。`supersedes` 走 freeform。
4. 盖 `cards.explore_id`，额外 fire `card_minted` 事件到 explore 的 `events.jsonl`。

### 验卡门（`ReviewService.create`，带 `explore_id` 时）

在现有 card-存在 / session-存在 / index 范围检查之后：
1. `req.session_id ∈ partition.posterior`，否则拒（边界/先验/不可见 session 一律拒）。
2. **被 review 的卡得能在本 explore 下被 review**：`card.explore_id == 本 explore` **或** `card.explore_id IS NULL`。这让**整个已有的 freeform 卡库**也能拿进来用后验验证（你说的「抽 card…然后 review」对工厂外的旧卡也成立），同时仍禁止跨 explore 串台（拿 explore-A 的卡在 explore-B 下 review）。
3. 盖 `reviews.explore_id`，额外 fire `review_filed` 事件。

review 是 append-only 不可改的——所以两道门都在**写之前**跑。

## validated 视图——精确定义

修掉「validated 把三件事混为一谈」「形状错（是矩阵不是布尔）」「没被验的卡消失了」三类发现。**关键：不把任何 *session* 叫「validated」。**

### 后验 session 行：叫 `spent`（花掉了），带极性

一个后验 session 的标记意思是**spent**（在本 explore 下被用作 review 证据 ≥1 次），**不是**「confirmed」。每个后验 session 给：

```
{ session_id, last_at, ts_confidence,
  spent: bool, reviews_filed: k,
  cards_reviewed: [...],      # 它对哪些卡表了态
  up, down, neutral }         # 它自己的 stance 分布
```

`unspent = 后验 \ {在本 explore reviews 里出现过的 session}` 作为一等列表显式给出（「你还没用过的后验 session」）。CLI 那列叫 **spent ✓/·**，**绝不**叫 validated。

### 每张卡行：以 `cards` 为主、LEFT JOIN reviews（没被验的卡不消失）

以 card 为主表 LEFT JOIN（沿用 `CardStore.list_cards` 的 idiom）。一张抽出来、零后验 review 的卡，显示成全 0 + `status = untested`——这是工厂**最该看的信号：你还没验的库存**。

**(session × card) 去重**（修双计数）：一个后验 session 可能对同一张卡先 +1 后 −1（append-only「改主意」）。explore 计票按 **distinct session、每个 `(session_id, card_id)` 取最后一次 stance**，同时报 `n_sessions`（去重的表态 session 数）和 `n_reviews`（原始条数）。卡的判定用 `n_sessions`，免得一个反复横跳的 session 虚增深度。

### 每张卡的 `status`（明确判定规则）

```
untested  : n_sessions == 0
neutral   : n_sessions > 0 且 up==0 且 down==0     # 只有耸肩
confirmed : up > down 且 up > 0
refuted   : down > up
contested : up == down 且 up > 0
```
neutral(0) 算**覆盖**（有人看过）但**不**算确认/否定。这个 status 是 **explore 局部**判定。

### 局部 vs 全局，要标注不要藏

explore 计票只数 `reviews WHERE explore_id`；全局 `card_stats` 仍聚合**所有** review（沉浮信号，绝不分区）。两者可能不一致（explore 说 `+2/−0`，终身 `+2/−5`）。视图明确标成「本 explore 的后验 review」，旁边给终身值当上下文：`本 explore: +2/−0 · 终身: +2/−5`——别让人把局部判定当成卡的真实地位。

## 对象模型 + 存储

**版本**：新表 + 加列 = **minor bump**（schema 变更，符合「版本号只跟数据结构变」的规约）。

```sql
CREATE TABLE explores (
  explore_id        TEXT PRIMARY KEY,   -- explore_<ulid>
  anchor_session_id TEXT NOT NULL,
  divider_at        TEXT NOT NULL,      -- 锚点 last_at，canonical Z，冻结
  created_at        TEXT NOT NULL,      -- T_explore
  ceiling_at        TEXT NOT NULL,      -- = created_at
  note              TEXT
);
ALTER TABLE cards   ADD COLUMN explore_id TEXT;   -- NULL = freeform
ALTER TABLE reviews ADD COLUMN explore_id TEXT;   -- NULL = freeform
```

每张卡/每条 review 至多属于一个 explore → 用可空列，不用 join 表。

**文件镜像 + 事件**（house style，`repository/explores.py` 新增 `ExploreStore`）：
```
explores/<bucket>/<explore_id>/explore.json     ← 不可变 manifest（冻结快照，唯一权威）
explores/<bucket>/<explore_id>/events.jsonl     ← created / card_minted / review_filed
```
`explore.json` 冻结三张分区表，每个先验 session 带 `round_count_at_snapshot` + `ts_confidence`。

## API / CLI 面

- **复用现有写端点**：`CreateCardRequest` / `CreateReviewRequest` 加一个可选 `explore_id`；带了就启动防火墙 + 盖戳。**不新增**抽卡/验卡端点，文件镜像/事件/stats/向量写全不变。
- **新对象端点**用**复数 `/v3/explores`**（id 寻址），和已占用的 `/v3/explore/*`（agent feed）**前缀分开**避撞：
  - `POST /v3/explores {anchor_session_id, note?}` → `{explore_id, divider_at, prior/posterior/boundary_count, warnings[]}`
  - `GET /v3/explores/{eid}` → manifest + 每 session(spent) + unspent[] + 每卡(status, 计票)
  - `GET /v3/explores?limit=` → 列表，新→旧
  - 创建响应里 `posterior_count==0` → 警告「没有后验，无法 review，挑更早的锚点」；`prior_count<=1` → 警告「只有锚点可抽卡」。不硬拒（提前于未来 session 拍的快照是合法的）。
- **CLI** `cli/explore.py`（瘦客户端）：`explore create <anchor> [--note]` / `explore view <eid>` / `explore list`。抽卡/验卡走现有 `card create` / `review create` 加 `--explore <eid>` 糖注入 `explore_id`——**一条抽卡路径、一条验卡路径**。

## 与 DAG / recall / searchbase 的关系

- **血缘 DAG**：结构不变；explore 只是给 `source_cards` 加了一道**正交的时间门**（`derives_from` 父卡须先验接地、`supersedes` 禁用）。不加边、无环险，成员归属只是个 tag。
- **recall**：无需改。recall 已经把 explore-*命名空间的 session* 滤掉了；卡上的 `explore_id` 戳是惰性元数据，recall 不必读。（可选未来：「只 recall explore X 的卡」。）
- **searchbase / LanceDB**：零新增。卡只 embed insight 文本（`explore_id` 不进 embedding）；explore 对象按 id 查、不做语义检索——**无新表、无 embedding 迁移**。`explore_id` 纯活在 SQLite + JSON 镜像。

## 仍待定

§时间/分区/视图/防火墙都被验证settle了。下面是真正要人拍板的：

1. **改名？** 「explore」一词双重占用（agent workspace vs 工厂对象）。靠 `/v3/explores` 复数前缀能安全发车，但要不要干脆把对象改名 **Retro / Snapshot / Lens**（公共面更干净、一次性成本）？这是定 CLI/HTTP 面之前要拍的。
2. **round 粒度防火墙**确认：§防火墙 step 2 是按 round 卡（`index <= round_count_at_snapshot`），意味着一个跨界长 session 有些 round 能引、有些不能，整 session 归桶只用于显示。这贴合你「引用须先验」的 round 级原话，但是个落在不可改 review 背后的语义承诺，确认是这个读法。（边角：先验 session 里 `timestamp=None` 的 round 当前按「在快照内即先验」收入；若想把 null 时间戳的 round 排除，说一声。）
3. **boundary 桶 UX**：机制定死了（非锚点、`last_at==divider_at` 进 boundary，两边都不能用）。开放：CLI 要不要让人在创建时**手动**把 boundary session 拨进先验或后验？默认：惰性 + 显式列出。
4. **要不要派生 `sessions.last_at` 列**：创建时现在要逐个读 `rounds.jsonl` 算 `last_at`（O(N) jsonl 读）。加个 append 时维护的派生列能让候选扫描纯 SQL。**若加，必须和上面 `compute_session_last_at` 逐位一致**，且它是**当前值、对已建 explore 的成员判断永不参与**。建议加（并入同一个 minor bump），但属性能/范围权衡，非正确性。
