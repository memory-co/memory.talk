# review

对一个**答案(Position)**的"回帖"——表态它对不对,可以**支持(+1)、中立(0)、反对(−1)**,附带某次 session 的证据 rounds 和一句说明。

沿用 v3 的 review 机制,只把对象从整张卡**下放到 Position**:同一个问题下的不同答案各自被顶踩、各自竞争。`argument ≠ 0` 的 review 就是一条 **IBIS Argument**(顶 = pro / 踩 = con);`argument = 0` 是中立观察。

```bash
memory.talk review <position_id> <+1|0|-1> --cite <session_id>:<indexes> [--comment '<一句话>'] [--json]
```

## 参数

| 参数 | 必填 | 说明 |
|---|---|---|
| `<position_id>` | 是 | 被表态的答案,必须是 `pos_<…>`;不存在或前缀错报错。**target 是 Position,不是 card** |
| `<argument>` | 是 | `+1` 支持(顶) / `0` 中立 / `-1` 反对(踩)。其它值报错 |
| `--cite` | 是 | 证据:`<session_id>:<indexes>`,**单 session**(一次表态来自一次具体对话);indexes 语法同 [card.md](card.md#--source-语法--indexes) |
| `--comment` | 否 | 一句话归因;`argument=0` 时强烈建议填,服务端不强制。值支持 `@<file>` / `@-`(从文件 / stdin 原样读,专治特殊字符;同 [card.md](card.md#文本字段传文件--stdin)) |
| `--review_id` | 否 | 不提供则自动生成 `review_<ULID>` |

> **单 session**:跟答案的出处(`card_sessions` 可多 session)不同,一条 review 只挂一个 session——它是"某次对话里对某个答案的一次表态"。
>
> 同一对 `(position_id, session_id)` **可有多条 review**(一次对话里早期反对、深入后转支持),由不同 `indexes` 区分,服务端**不去重**。

完整字段语义见 [`../../structure/v4/review.md`](../../structure/v4/review.md)。

## 输出 — Markdown(默认)

````markdown
ok: created `review_01jzr5kq` · `pos_01jzp3nq` **+1** by `sess_abc` #20-25
````

错误(到 stderr,exit 1):

````markdown
**error:** argument must be one of +1, 0, -1 (got 2)
````

````markdown
**error:** position `pos_01jzNotExist` not found
````

## 输出 — JSON(`--json`)

```json
{
  "status": "ok",
  "review_id": "review_01jzr5kq",
  "position_id": "pos_01jzp3nq",
  "card_id": "card_01jz8k2m",
  "session_id": "sess_abc",
  "argument": 1
}
```

```json
{"error": "argument must be one of +1, 0, -1 (got 2)"}
```

`card_id` 回显 = 该 Position 所属卡(冗余,方便对账)。

## 副作用

- 校验:`position_id` 存在;`session_id` 存在且 `indexes` 不越界;`argument ∈ {-1,0,1}`。任一失败,整条不落库。
- **累加该 Position 的计数**(原子 upsert):
  - `argument = +1` → `up_count += 1`
  - `argument = -1` → `down_count += 1`
  - `argument = 0` → `neutral_count += 1`
- **不写 credence**——credence 是读 / 排序时按 `up − down`(或 Wilson)现算,没有要 bump 的列。
- 落 review 到 SQLite `reviews` 表(`position_id` + 冗余 `card_id` + `session_id` + `indexes` + `argument` + `comment`);review 沿用 v3 的存法,有自己的 canonical。
- review 自身**不进向量索引**——`comment` 是辅助说明,检索按卡的 `issue` 匹配。

## 中立(argument=0)堆多了 → 可能衍生新 Position

一条中立 = "证据跟这个问题相关,但不站现有任何答案的队"。一张卡积累一批中立,说明现有答案没接住这些证据——可能在为一个**还没说出来的答案**背书。可**离线**(人 / LLM 判)把这堆中立聚类,提一个新 Position(`card position --card <同卡> --answer ...`),再把这些 review 以 `+1` 重挂到新答案上。**不自动**触发。详见 [`../../works/v4/card.md`](../../works/v4/card.md#3-第二推credence--现算的质量分相关性只在召回时算)。

## 错误

| 情况 | 状态 / 消息 |
|---|---|
| `position_id` 缺失 / 前缀错 | `invalid position_id prefix` |
| `position_id` 不存在 | `position <pid> not found` |
| `argument` 非 +1/0/-1 | `argument must be one of +1, 0, -1 (got <v>)` |
| `--cite` 的 session 不存在 | `session <sid> not found` |
| `--cite` 的 indexes 越界 / 非单调 | `index N out of range ...` / `indexes must be monotonically increasing` |
| `--review_id` 已存在 | `review_id already exists`(409) |

## 读取

review **不单独 read** —— 在 [`card view <card_id>`](card.md#card-view) 的每个 Position 块里以顶踩计数体现;raw 列表走 `card view <cid> --json` 或直查 SQLite。

## 跟 card 的边界

| | `card position` | `review` |
|---|---|---|
| 角色 | 立一个答案(候选) | 对答案的后续表态 |
| 时序 | 先 | 后(Position 必须已存在) |
| session 引用 | 出处 `card_sessions`,可跨多 session | 证据单 session |
| 内容载荷 | `claim`(答案文本) | `argument` + `comment` |
| 进向量 | 卡的 `issue` 进 | 否 |
| 增删改 | append-only | append-only(撤销 = 写一条相反 argument 的) |

## 推荐姿势

```bash
# 又一次验证了某个答案
memory.talk review pos_01jzp3nq +1 --cite "$SID:20-25" --comment '再次确认,简洁版接住了'

# 某个答案被这次对话证伪
memory.talk review pos_01jz0xnq -1 --cite "$SID:3-8" --comment '纯简洁漏了调试细节'

# 相关但不站队(中立观察)
memory.talk review pos_01jzp3nq 0 --cite "$SID:11" --comment '又提到这个问题,但没改变结论'
```
