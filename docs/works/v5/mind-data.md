# mind-data — card 库:IBIS 信念数据(v5 设计)

> **状态:设计中。** [query-interface](query-interface.md) 两库分治里的 **card 库**——**mind(信念)侧**:harness 从经验里结晶出的问题图(IBIS),**只有 harness 经受治理写动作可写**,是它治理的本职对象。本篇给出**具体表设计**;对应的经验侧见 [reality-data.md](reality-data.md)。

相关:
- 两库分治的总述(谁读谁写、跨库 join): [query-interface.md](query-interface.md)
- 引擎(表声明 / searchable / files 镜像 / 时光机都由它兑现): [seekbase.md](seekbase.md)
- IBIS 语义的来处(v4 设计,本篇是它的 v5 关系化): [../v4/card.md](../v4/card.md) · [../v4/session-mark.md](../v4/session-mark.md)

---

## 1. 定位与不变性

**mind 库里是判断,不是事实**:card(问题)、position(答案)、review(表态)、link(边)、mark(读经验时的标注)。继承 v4 的 IBIS 不变性,并按 v5 的引擎能力收紧:

1. **append-only**:一切对象只增不改;「改主意」= 加新对象 + 踩旧的;删除 = 墓碑(`deleted_at`,seekbase 时光机 §7),不物理删;
2. **派生值不落表**(比 v4 更彻底,§3):credence、各计数一律视图现算——v4 的 `up_count` 等物化计数列**退役**;
3. **寻址 ↔ 复合键**:`card_x#p1` ↔ `(card_id,'p1')`、`card_x#l2` ↔ `(card_id,'l2')`、`sess_y#m2` ↔ `('session','sess_y','m2')`;
4. **对 reality 只有软引用**:证据定位(`ref` / `indexes`)指向 [reality 库](reality-data.md),无 FK、容忍悬空,mind 永远不写 reality;
5. **证据统一 `(type, ref)` 模式**:凡指向证据源的地方(proofs / reviews 引证 / marks 标注对象)都用 `type`(`'session'` 当前唯一,`'file'` 等为进化预留)+ `ref`(该型的定位;session 型 = `session_id`)——**mind 不焊死「证据只能来自 session」**,新证据源 = 加一个 type 值,表结构与查询面不动。

## 2. 表设计

```sql
-- ═══ 问题图 ═══
CREATE TABLE cards (
  card_id     TEXT PRIMARY KEY,      -- card_<ULID>
  issue       TEXT NOT NULL,         -- 问题文本(embedding 锚点,不可变)
  created_at  TEXT NOT NULL,
  deleted_at  TEXT                   -- 墓碑(下同;v4 的 position_count/link_count 退役 → 视图数)
);

CREATE TABLE positions (
  card_id     TEXT NOT NULL,
  position    TEXT NOT NULL,         -- 'p<n>',卡内序号(mint = max(seq)+1,墓碑不复用号)
  claim       TEXT NOT NULL,         -- 答案文本(不可变)
  scope       TEXT NOT NULL DEFAULT '',
  forked_from TEXT,
  created_at  TEXT NOT NULL,
  deleted_at  TEXT,
  PRIMARY KEY (card_id, position)    -- ↔ card_x#p1(v4 的 up/down/neutral/review_count 退役)
);

CREATE TABLE reviews (               -- 表态 = 一等事件(计数/credence 都从这现算)
  review_id   TEXT PRIMARY KEY,      -- review_<ULID>
  card_id     TEXT NOT NULL,
  target      TEXT NOT NULL,         -- 'p<n>' | 'l<n>'
  target_kind TEXT NOT NULL,         -- position | link
  proof_type  TEXT NOT NULL,         -- 引证的证据类型:'session'(当前唯一)| …(§1.5)
  proof_ref   TEXT NOT NULL,         -- 证据定位:session 型 = session_id(软引用 reality)
  indexes     TEXT NOT NULL,         -- 证据位置:session 型 = rounds('11-15' / '3,7,12')
  argument    INTEGER NOT NULL,      -- +1 | 0 | -1
  comment     TEXT,
  created_at  TEXT NOT NULL,
  deleted_at  TEXT
);

CREATE TABLE card_links (            -- 受治理的 IBIS 边,本身是主张
  card_id     TEXT NOT NULL,         -- 主体卡
  link        TEXT NOT NULL,         -- 'l<n>',卡内序号
  type        TEXT NOT NULL,         -- specializes / questions / replaces / suggested_by …
  target_id   TEXT NOT NULL,         -- 另一张卡;仅 suggested_by 可指 card_<…>#p<n>
  target_type TEXT NOT NULL,         -- card | position(由 target_id 派生)
  claim       TEXT NOT NULL,         -- 这条边为什么成立(不可变;计数列同样退役)
  created_at  TEXT NOT NULL,
  deleted_at  TEXT,
  PRIMARY KEY (card_id, link)        -- ↔ card_x#l1;UNIQUE (card_id, type, target_id) 幂等
);

-- ═══ 出处(provenance;session 型的 ref 软引用 reality)═══
CREATE TABLE card_proofs (           -- 卡的证据(泛化出处):这张卡因何被建 / 被连
  card_id    TEXT NOT NULL,
  type       TEXT NOT NULL,          -- 证据类型:'session'(当前唯一)| 'file' | …(为进化预留)
  ref        TEXT NOT NULL,          -- 证据定位:type=session → session_id;type=file → 路径(未来)
  mark       TEXT NOT NULL DEFAULT '', -- type=session 必填('m<n>',哪次 mark);其他型空串
  indexes    TEXT,                   -- type=session:#…？ grounding 的 round(s)
  created_at TEXT NOT NULL,
  PRIMARY KEY (card_id, type, ref, mark)
);
-- (type, ref) 统一证据模式见 §1.5;session 型由 mark 写路径产生,mark/indexes 按型校验必填。
CREATE TABLE position_proofs (       -- 答案的证据:从哪长出来(indexes 必填,mark 可选)
  card_id TEXT NOT NULL, position TEXT NOT NULL,
  type TEXT NOT NULL, ref TEXT NOT NULL,        -- (type, ref) 同 §1.5
  indexes TEXT NOT NULL, mark TEXT, created_at TEXT NOT NULL
);
CREATE TABLE link_proofs (           -- 边的证据
  card_id TEXT NOT NULL, link TEXT NOT NULL,
  type TEXT NOT NULL, ref TEXT NOT NULL,
  indexes TEXT NOT NULL, created_at TEXT NOT NULL
);

-- ═══ 结晶标注(mark:一次「读完整个证据源」的逐单元判断;源当前只有 session)═══
CREATE TABLE marks (
  type        TEXT NOT NULL,         -- 被标注的证据源类型:'session'(当前唯一)| …(§1.5)
  ref         TEXT NOT NULL,         -- 证据源定位:session 型 = session_id(软引用 reality)
  mark        TEXT NOT NULL,         -- 'm<n>',服务端分配,(type, ref) 内递增
  last_index  INTEGER NOT NULL,      -- 乐观锁基线(标注时源有几个单元;session 型 = 轮数)
  description TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  deleted_at  TEXT,
  PRIMARY KEY (type, ref, mark)      -- ↔ sess_y#m2(session 型)
);
CREATE TABLE mark_rounds (           -- 逐单元:idx 从 1 起严格递增,覆盖 ≥90%(session 型 = round)
  type TEXT NOT NULL, ref TEXT NOT NULL, mark TEXT NOT NULL, idx INTEGER NOT NULL,
  comment TEXT,                      -- 可空 = 读了没东西标(只占覆盖)
  PRIMARY KEY (type, ref, mark, idx)
);
CREATE TABLE mark_issues (           -- #…？/ 主动声明 issue 的撞库结果(card_id/is_new 服务端回填)
  type TEXT NOT NULL, ref TEXT NOT NULL, mark TEXT NOT NULL, idx INTEGER NOT NULL,
  issue TEXT NOT NULL, card_id TEXT NOT NULL, is_new BOOLEAN NOT NULL,
  indexes TEXT NOT NULL
);
```

**计数列退役**是本篇对 v4 最大的结构改动:`reviews` 本来就是 append-only 事件,计数与 credence **全部从它现算**(§3)——写路径不再 bump 任何计数(v4 的原子 upsert 消失),as-of 时光机下的历史值天然精确(seekbase §7 的「事件化」纪律),`p<n>`/`l<n>` 的 mint 改为 `max(seq)+1`(墓碑不复用号)。

## 3. 视图:口径的唯一出处

```sql
CREATE VIEW v_positions AS           -- 计数 + credence 现算(review 事件聚合)
  SELECT p.*,
         count(r.review_id) FILTER (WHERE r.argument = 1)  AS up_count,
         count(r.review_id) FILTER (WHERE r.argument = -1) AS down_count,
         count(r.review_id) FILTER (WHERE r.argument = 0)  AS neutral_count,
         count(r.review_id)                                AS review_count,
         count(r.review_id) FILTER (WHERE r.argument = 1)
       - count(r.review_id) FILTER (WHERE r.argument = -1) AS credence
  FROM positions p
  LEFT JOIN reviews r ON r.card_id = p.card_id AND r.target = p.position
                     AND r.target_kind = 'position' AND r.deleted_at IS NULL
  WHERE p.deleted_at IS NULL GROUP BY ALL;

CREATE VIEW v_links AS …;            -- 同构(target_kind = 'link')
CREATE VIEW v_cards AS …;            -- cards + 现算 position_count / link_count
CREATE VIEW v_card_best AS           -- 每卡当前最优答案
  SELECT * FROM v_positions
  QUALIFY row_number() OVER (PARTITION BY card_id ORDER BY credence DESC, created_at) = 1;
CREATE VIEW v_links_in AS            -- 入边反查(target 侧视角)
  SELECT target_id AS card_id, card_id AS from_card, link, type, claim
  FROM card_links WHERE deleted_at IS NULL;
CREATE VIEW v_card_provenance AS     -- 卡 ← mark ← 证据源 一步到位(全型通用)
  SELECT p.card_id, p.type, p.ref, p.mark, p.indexes, m.description, m.created_at
  FROM card_proofs p JOIN marks m USING (type, ref, mark);
```

视图是 mind 库的**第二层契约**:表保「摊平的事实性记录」,视图保「不该被重复推导的口径」(credence 怎么算、最优怎么取、入边怎么反查)——口径变了改视图,一处生效。

## 4. seekbase 声明(searchable)

| 表 | searchable(自动 embed) |
|---|---|
| cards | `issue`(`#…？` 撞库判新撞的就是它) |
| positions | `claim` |
| 其余(reviews / links / 出处 / marks 三表) | — |

> 文件镜像(`files` 声明)、墓碑、时光机是 **seekbase 的通用机制**([seekbase §6/§7](seekbase.md)),不在业务数据篇重复;路径模板到实现时在 schema 声明里给。

## 5. 写动作面(唯一的写门)

mind 库**只接受受治理写动作**(SQL 面只读,见 query-interface §2):`create_card` / `add_position` / `review` / `link` / `submit_mark`(逐 round、≥90% 覆盖、`#…？` 撞库)/ `merge` / `decay` / `delete`(墓碑级联)。每个动作 = seekbase 一次原子写(引擎内政),不变性(append-only、撞库判新、id 单调)全部在动作里兑现。

## 6. 待定

- **mark_issues 与 card_proofs(session 型)的重叠**:都记「mark→card」,前者带轮级细节、后者聚合出处——留双份还是视图化其一;
- **file 型证据的语义**:idx / indexes 在 file 型下指什么(行号?段落?),`last_index` 怎么取——等第一个非 session 证据源出现时定;
- **credence 公式演进**:up−down 之外(Wilson / 时间衰减)——好在只改视图;
- **merge / decay 的表达**:seekbase 焊死 insert-only 后基本定向——合并 = 新对象 + `replaces` 边 + 旧卡墓碑(`merged_into` 列那种就地改写不存在了);衰减若要留痕,落事件表;
- **计数视图性能**:corpus 大后 v_positions 的聚合要不要物化(DuckDB 物化视图 / 增量表)——先现算,量到了再说。

## 与其他 v5 文档的关系

- [reality-data.md](reality-data.md):它是证据、我是判断;我软引用它,永不写它。
- [query-interface.md](query-interface.md):我的表 + 视图就是它 SQL 契约的 mind 半边。
- [memory-harness.md](memory-harness.md):harness 的受治理写动作全部落在本库;它对 reality 只读。
