# Recall-Result (v4)

`POST /v4/recall` 的返回结构 —— 召回阶段(hook 无意识注入)把命中卡底下的 Position 排好序、连 `scope` 软提示一起交给 LLM 的那份载荷。

读路径机制见 [`../../works/v4/card.md`](../../works/v4/card.md) §7;API 见 [`../../api/v4/recall.md`](../../api/v4/recall.md);CLI 见 [`../../cli/v4/recall.md`](../../cli/v4/recall.md)。

## 召回怎么算出来的

```
召回   : context → embed → 撞卡的问题(cards collection:向量 + FTS)→ 取命中卡底下的 Position
         (「相不相关」就在这一步由检索算清,不读任何存储字段)
排序   : 命中的 Position 按现算校验分(credence = f(up_count, down_count),如 up−down / Wilson)
         排序;平手用「最近更新」(该 Position 最后一条 review 的 created_at)tiebreak
注入   : 一张卡通常只取 credence 最高的那个(= 当下答案);每个 Position 连同它的 scope 一起给 LLM
```

**位(scope)不是门禁**:不按 scope 挡卡,而是把 scope 作为软提示随答案注入,让 LLM 自判当前语境合不合 —— 跨界默认放行。**没有 `accepted` 状态**:「当下答案」就是 credence 现算最高的那个。

## Schema

```json
{
  "session_id": "sess_def456",
  "cards": [
    {
      "card_id": "card_01jz8k2m",
      "issue": "用户偏好什么回答风格?",
      "relevance": 0.83,
      "answer": {
        "position_id": "pos_01jzr5kq",
        "claim": "简洁优先 —— 默认给结论,展开按需",
        "credence": 0.78,
        "up_count": 7,
        "down_count": 1,
        "neutral_count": 2,
        "scope": "日常技术问答场景;复杂决策题不适用——那种要展开。"
      },
      "alternatives": [
        {
          "position_id": "pos_01jzp3nq",
          "claim": "看场景 —— 简单题简洁,决策题详细",
          "credence": 0.62,
          "scope": ""
        }
      ]
    }
  ]
}
```

## 字段

### 顶层

| 字段 | 类型 | 说明 |
|---|---|---|
| `session_id` | string | 本次召回所在 session(去重用,沿用 v3 recall 同 session 内去重) |
| `cards` | Card[] | 命中的卡,按 `relevance`(检索相关性)倒序 |

### 每张命中卡

| 字段 | 类型 | 说明 |
|---|---|---|
| `card_id` | string | `card_<...>` |
| `issue` | string | 问题文本(就是被撞中的检索锚点) |
| `relevance` | float | 检索相关性(向量 + FTS),**召回时现算**,不落库 |
| `answer` | Position | credence 最高的 active Position(= 当下答案);卡下无 Position 时为 `null` |
| `alternatives` | Position[] | 其余竞争答案,按 credence 倒序;可空数组。注入时通常只用 `answer`,`alternatives` 供需要全局视角时取用 |

### Position(召回视图)

| 字段 | 类型 | 说明 |
|---|---|---|
| `position_id` | string | `pos_<...>` |
| `claim` | string | 答案文本 |
| `credence` | float | **现算**校验分(= f(up, down));不是存储字段 |
| `up_count` / `down_count` / `neutral_count` | integer | 顶踩计数(`answer` 给全,`alternatives` 可精简) |
| `scope` | string | 适用场景软提示;随答案注入,LLM 自判,不挡 |

## 排序与去重

- **卡间**:按 `relevance`(检索相关性)排。
- **卡内 Position**:按 `credence` 现算排,平手按最近更新(最后一条 review `created_at`)。
- **同 session 去重**:同一 session 内不重复注入同一张卡(沿用 v3 `recall_log` 思路;v4 不回写任何 engagement 计数 —— recall 不进 `up/down`,也不存 recall_count)。

## 跟 v3 recall 的差异

| | v3 recall | v4 recall |
|---|---|---|
| 返回单元 | 整张 card(一句 insight) | 卡(问题)+ 它的 answer / alternatives(答案们) |
| 卡内选谁 | 没有「卡内」概念 | credence 现算最高的 Position(平手 recency) |
| 排序信号 | 沉浮公式(吃 review + read + recall + age) | 卡间相关性 + 卡内 credence;均现算 |
| 副作用 | bump `recall_count`(engagement) | **不回写任何计数** —— recall 是路过,不算讨论 |
| 适用域 | 无 | `scope` 软提示随答案注入(不挡) |
