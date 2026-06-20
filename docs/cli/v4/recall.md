# recall

无意识召回:hook 阶段拿当前 prompt 去**撞问题图**,把命中卡的当下答案极简注入 LLM context。沿用 v3 recall 的"无意识、极简"姿态,只是从"撞陈述"变成"撞问题 → 取答案"。

```bash
memory.talk recall --session <session_id> --prompt '<prompt>' [--json]
```

## 参数

| 参数 | 必填 | 说明 |
|---|---|---|
| `--session` | 是 | 当前所在 session(`sess_<…>`),用于同 session 去重 |
| `--prompt` | 是 | 当前 context / 用户 prompt 文本,作召回 query。值支持 `@<file>` / `@-` |

## 召回流程

```
召回   : prompt → embed → 撞 issue + claim(向量 + FTS)→ 命中的 Position(争议卡里贴 context 的那侧排上来)
         (相不相关就在这一步由检索算清,不读任何存储字段)
排序   : 命中卡的 Position 按现算校验分(up − down / Wilson)排序,平手用最近更新
         (最后一条 review 时间)tiebreak;一张卡通常只取最高的那个 = 当下答案
注入   : 按校验分进 context —— 每个答案连同它的 scope(适用场景)一起给 LLM
         (scope 是软提示,让模型自判语境合不合,不机械挡;跨界默认放行)
```

**位不是门禁**:`scope` 不挡卡——它随答案一起注入,让 LLM 自己判当前语境合不合。一个过期 / 不太对的答案,只在它被后续 `review` 踩、credence 现算掉下去之后才不再浮上来。详见 [`../../works/v4/card.md`](../../works/v4/card.md#7-读路径--dto)。

## 输出 — Markdown(默认)

`````markdown
# recall · 2 cards

### 用户偏好什么回答风格?
默认简洁、要点优先
`scope: 日常问答;调试/教学场景另说` · `card_01jz8k2m`

### 提交信息怎么写?
祈使句、首行 ≤ 50 字、正文说清 why
`card_01jzcm7`
`````

- 一行问题(`issue`)、一行当下答案(`claim`,credence 最高的那个)、一行 `scope`(空则省)+ 卡 id。
- 极简:hook 阶段不堆元数据(不出 credence / 计数),只给 LLM "问题 + 当下答案 + 适用场景"。

## 输出 — JSON(`--json`)

```json
{
  "session_id": "sess_ghi",
  "cards": [
    {
      "card_id": "card_01jz8k2m",
      "issue": "用户偏好什么回答风格?",
      "position": {
        "position": "p1",
        "claim": "默认简洁、要点优先",
        "scope": "日常问答;调试/教学场景另说",
        "credence": 6
      }
    }
  ]
}
```

- 默认每张命中卡只回**当下答案**(credence 最高的那个 Position)。
- `credence` 是响应里现算的(不在存储)。
- 召回结果结构见 [`../../structure/v4/recall.md`](../../structure/v4/recall.md)。

## 去重

同一 `session_id` 内已经召回过的卡不重复注入(沿用 v3 recall 去重),避免一个 session 里反复推同一张卡。

## 错误

| 情况 | 行为 |
|---|---|
| server 未运行 | `error: cannot reach server`,exit 1 |
| `--session` 前缀错 | `error: invalid session_id prefix`,exit 1 |
| `--prompt` 为空 | `error: --prompt required`,exit 1 |

## 跟 search 的边界

| | `recall` | `search` |
|---|---|---|
| 触发 | hook 阶段无意识 | 用户 / agent 有意识 |
| 输出 | 极简(问题 + 当下答案 + scope) | 完整(可带 DSL 过滤、多答案) |
| 排序 | 检索相关性 → credence(取当下答案) | 见 [`search`](search.md) |
| 用途 | 注入 context | 检索 / 排查 |

`search` 的完整契约见 [`search.md`](search.md)。
