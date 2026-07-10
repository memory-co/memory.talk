# cards — mind 库的受治理写动作(v5 API)

mind 库唯一的写门([mind-data §5](../../works/v5/mind-data.md)):每个动作 = seekbase 一次原子写(insert-only,不变性在动作里兑现)。**动作按 agent 实例挂载**——完整路径是 `/v5/agents/{name}/…`(下文省略前缀),**只有该 agent 自己调**、只写**它自己的** mind 库;证据一律 `(type, ref, indexes)` 模式([structure](../../structure/v5/README.md))。

## POST …/cards — 建卡(撞库判新内建)

```json
{ "issue": "为什么 pty 会让用户想到 tmux？",
  "proofs": [{ "type": "session", "ref": "sess_def456", "indexes": "36-37" }] }
```

服务端先 embed `issue` 撞 issue 库:**miss → 建新卡;hit → 不建、返回既有卡**——「新不新交给检索、不让 AI 自评」的纪律在动作里兑现。

响应:`{"card_id": "card_01j…", "is_new": true}`(hit 时 `is_new: false` + 命中卡 id;proofs 两种情况都落)。

## POST …/cards/{card_id}/positions — 加答案

```json
{ "claim": "他要的是可重连会话,不是 pty 本身",
  "scope": "",                          // 可选
  "proofs": [{ "type": "session", "ref": "sess_def456", "indexes": "36-41" }] }
```

→ `{"card_id": …, "position": "p1"}`(序号服务端 mint,寻址 `card_x#p1`)。`proofs` 必填(答案必须有出处)。

## POST …/reviews — 表态(对答案或边)

```json
{ "target": "card_01j…#p1",             // #p<n> 或 #l<n>,分片定 target_kind
  "argument": 1,                         // +1 | 0 | -1
  "proof": { "type": "session", "ref": "sess_abc", "indexes": "20-25" },
  "comment": "再次确认,简洁版接住了" }
```

→ `{"review_id": "review_…"}`。单条引证(一次表态一份证据);计数 / credence 不写任何列(视图现算)。

## POST …/cards/{card_id}/links — 连边

```json
{ "type": "specializes", "target_id": "card_09a…",
  "claim": "两卡同一套 auth,这张是特化",
  "proofs": [{ "type": "session", "ref": "sess_abc", "indexes": "30-34" }] }
```

→ `{"card_id": …, "link": "l1"}`;UNIQUE `(card_id, type, target_id)` 幂等(重复连边返回既有 `l<n>`)。

## DELETE …/cards/{card_id} — 墓碑级联

`?dry_run=true` 先预览计数(positions / reviews / links 出入边 / proofs / vectors),真删 = **全部打墓碑**(insert-only,无物理删;时光机可回放)。响应 `{card_id, deleted:{…}}` / dry-run `{card_id, issue, counts:{…}}`;404 卡不存在。

## POST …/cards/{survivor}/merge — 合并(B 级动作,默认在环)

```json
{ "absorbed": "card_09a…", "claim": "两问实为同一个:pty 可重连的本质诉求" }
```

三步机械语义([actions §2](../../works/v5/actions.md)):`replaces` 边(claim 必填,受治理)→ absorbed 的 proofs 并入 survivor → absorbed 及其 positions / links 级联墓碑。**答案不自动搬**(要留的答案 merge 前自行 `add_position(forked_from=…)`)。幂等;时光机可回放合并前。→ `{survivor, absorbed, merged: true}`。

## POST …/decay — 衰减(append 事件)

```json
{ "target": "card_01j…#p1", "amount": 1, "reason": "180 天无新证据" }
```

append 一条 `decay_events`;credence 视图口径 = `up − down − Σ decay`(**不碰 reviews**,表态史干净);反悔用负 `amount` 冲销([actions §3](../../works/v5/actions.md))。→ `{target, decay_total}`。

> **权属分级**([actions §4](../../works/v5/actions.md)):create/position/review/link/decay 为 **A 级(自主)**;merge / delete 为 **B 级(在环)**——初期须经 chat 请示确认,放权按实例配置。
