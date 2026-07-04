# mind 库 — 字段契约(v5)

信念侧:agent 结晶出的 IBIS 问题图。**每个 [agent](../../works/v5/agent.md) 实例一个独立的 mind 库**(按本契约各建一套);**只有所属 agent 经[受治理写动作](../../api/v5/cards.md)可写**;SQL 面只读。设计推理与 DDL 出处:[works/v5/mind-data.md](../../works/v5/mind-data.md)。引擎通用列(`created_at` / `deleted_at`)与不变性见 [README](README.md),下面不重复。

## cards — 问题

| 列 | 类型 | 语义 |
|---|---|---|
| `card_id` | TEXT PK | `card_<ULID>` |
| `issue` | TEXT | 问题文本,**不可变**;embedding 锚点(建卡撞库撞的就是它) |

无计数列(`position_count` / `link_count` 在 `v_cards` 现算)。

## positions — 答案

| 列 | 类型 | 语义 |
|---|---|---|
| `card_id`, `position` | TEXT, TEXT · PK | `position` = `'p<n>'`,卡内序号(mint = max+1,墓碑不复用号);寻址 `card_x#p1` |
| `claim` | TEXT | 答案文本,不可变 |
| `scope` | TEXT | 适用场景(软提示,默认 `''`) |
| `forked_from` | TEXT? | 从哪个答案分叉(可空) |

无计数列(计数 / credence 在 `v_positions` 从 reviews 现算)。

## reviews — 表态(一等事件)

| 列 | 类型 | 语义 |
|---|---|---|
| `review_id` | TEXT PK | `review_<ULID>` |
| `card_id`, `target`, `target_kind` | TEXT×3 | 表态对象:`target` = `'p<n>'` / `'l<n>'`,`target_kind` = `position` / `link` |
| `proof_type`, `proof_ref` | TEXT×2 | 引证的证据源(`(type, ref)` 模式,见 [README](README.md)) |
| `indexes` | TEXT | 证据位置(session 型 = rounds) |
| `argument` | INTEGER | `+1` 支持 / `0` 中立 / `-1` 反对 |
| `comment` | TEXT? | 一句话归因 |

计数与 credence **全部**从本表现算——reviews 是 mind 库唯一的「值变化」来源。

## card_links — 边(受治理的主张)

| 列 | 类型 | 语义 |
|---|---|---|
| `card_id`, `link` | TEXT, TEXT · PK | `link` = `'l<n>'`;寻址 `card_x#l1`;UNIQUE `(card_id, type, target_id)` 幂等 |
| `type` | TEXT | `specializes` / `questions` / `replaces` / `suggested_by` … |
| `target_id`, `target_type` | TEXT×2 | 指向另一张卡;仅 `suggested_by` 可指 `card_…#p<n>`;`target_type` 派生 |
| `claim` | TEXT | 这条边为什么成立,不可变 |

## proofs 三表 — 证据链

| 表 | 键 | 语义 |
|---|---|---|
| `card_proofs (card_id, type, ref, indexes)` | PK `(card_id, type, ref)` | 这张卡因何被建 / 被连;同一证据源多次 grounding 合并进 `indexes` |
| `position_proofs (card_id, position, type, ref, indexes)` | — | 答案从哪长出来(`indexes` 必填) |
| `link_proofs (card_id, link, type, ref, indexes)` | — | 边的出处 |

> **没有 mark 表**:逐轮标注是 agent 的工作结构,由它自己长([mind-data](../../works/v5/mind-data.md));框架只保证证据链(本节)。lua harness 的 `engine_versions` 也落本库(实现时随 schema 声明)。

## 视图(口径的唯一出处)

| 视图 | 给什么 |
|---|---|
| `v_cards` | cards + 现算 `position_count` / `link_count` |
| `v_positions` / `v_links` | + 现算 `up/down/neutral/review_count` + **`credence`**(up−down) |
| `v_card_best` | 每卡当前最优答案(credence 最高) |
| `v_links_in` | 入边反查(target 侧视角) |
| `v_card_provenance` | 卡 ← 证据源(card_proofs 投影) |
