# Search Result

v4 搜索结果是**撞问题**检索的产物:一条结果 = 一张卡(Issue)+ 它的**当下答案**(`top_position`)+ 该答案的**现算 `credence`**。**没有 v3 那套沉浮 / forum 融合排序** —— `read_count` / `recall_count` 不存在,排序只在召回那一刻按检索相关性算,不回写任何"热度"信号。

## 结果结构

每条结果一张卡,核心字段:

| 字段 | 类型 | 说明 |
|---|---|---|
| `card_id` | string | 命中的卡(`card_<…>`) |
| `issue` | string | 卡的问题文本(检索锚点之一) |
| `position_count` | integer | 这张卡有几个答案;`0` = 还在等答案的问题 |
| `top_position` | object\|null | **当下答案** = 现算 `credence` 最高的 Position(平手按最近一条 review 时间);`position_count = 0` 时为 `null` |
| `score` | float | 检索相关性(向量 + FTS);`query` 为空串时省略 |
| `created_at` | string | 卡创建时间 |

`top_position` 内嵌该答案的快照:

| 字段 | 说明 |
|---|---|
| `position` | 答案在卡内的序号 `p<n>`(寻址 `card_id#position`;Position 无独立 id) |
| `claim` | 答案文本(内联) |
| `up_count` / `down_count` / `neutral_count` | 顶 / 踩 / 中立计数(存的) |
| `credence` | **现算**校验分(`up − down` / Wilson),不落库 |
| `scope` | 一句话适用场景(软提示) |

形态示例:

```json
{
  "card_id": "card_01jz8k2m",
  "issue": "用户偏好什么回答风格?",
  "position_count": 3,
  "top_position": {
    "position": "p1",
    "claim": "默认简洁、要点优先",
    "up_count": 7, "down_count": 1, "neutral_count": 0,
    "credence": 6,
    "scope": "日常问答;调试场景另说"
  },
  "score": 0.82,
  "created_at": "2026-06-18T14:30:00Z"
}
```

## 现算(不落库)

- **`credence`**:不是存储列,是响应里按 `up_count` / `down_count` 现算的派生值。排序、选「当下答案」都用它,但磁盘上没有这一列。
- **「当下答案」(`top_position`)**:命中卡的 Position 里 credence 最高的那个;无 `accepted` 标志位,平手按最近更新 tiebreak。
- **相关性 `score`**:只在召回那一刻按检索算,**不回写**、**不进任何持久排序**;`query` 空串时整字段省略(纯走 `where` DSL 过滤)。

要看一张卡的**全部**答案(不止当下答案)走 [`../../api/v4/read.md`](../../api/v4/read.md) `{id: card_…}`。

## 权威定义

- HTTP 响应形态 / `where` DSL 字段:[`../../api/v4/search.md`](../../api/v4/search.md)
- 卡 + Position + 现算 credence + 「当下答案」语义:[`card.md`](card.md)(见 Schema 小节与「现算(不落库)」小节)

> v4 把 v3 的沉浮三轴 / engagement 计数 / 融合排序公式**整套删掉**;命中卡带的是它的**当下答案** + 该答案的**现算 credence**,而不是一句陈述加 stats。
