# Recall API

## POST /v4/recall

hook 阶段的**无意识召回**：拿当前 context 撞**问题 + 答案**（`issue` + `claim` 两个向量库 + FTS），命中的 Position 按**检索相关性 + 现算校验分**排序（相关性选「哪一侧」、credence 选验证最好的），连各自的 `scope` 软提示注入 LLM context。争议卡里跟当前 context 最贴的那侧答案自然排上来。

跟 v3 recall 的关键差别：v4 召回到的是**答案候选(Position)**而非整卡，而且**位(scope)不再是门禁**——不机械挡卡，跨界默认放行，让 LLM 看着 scope 自己判语境。

CLI 对应 [`recall`](../../cli/v4/recall.md)。读路径全貌见 [`../../works/v4/card.md`](../../works/v4/card.md) §7。

### 请求体

```json
{
  "session_id": "sess_def456",
  "prompt": "用户当前这轮的话"
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `session_id` | 是 | 当前 session（同 session 内去重，沿用 v3 recall 行为） |
| `prompt` | 是 | 当前 context / prompt 文本，embed 后去撞 `cards`(`issue`)+ `positions`(`claim`)两个 collection |

### 流程（服务端）

```
召回   : prompt → embed → 撞 issue + claim(向量 + FTS)→ 命中的 Position(贴 context 的那侧排上来)
         (相不相关就在这一步由检索算清,不读任何存储字段)
排序   : 命中的 Position 按现算校验分(up−down / Wilson)排序;平手用最近一条 review 时间 tiebreak
         一张卡通常只取最高的那个(当下答案,非「采纳」状态)
注入   : 按校验分进 context —— 每个 Position 连同它的 scope(适用场景)一起给 LLM
         (scope 是软提示,让模型自判语境合不合,不机械挡;跨界默认放行)
```

> **没有"三道防火墙"**：v4 不建模时间(无过期门禁)、位是软提示(不挡)、势已删(相关性只在召回时由检索算、不回写)。召回排序就是检索相关性 + 现算 credence。

### 响应

```json
{
  "session_id": "sess_def456",
  "cards": [
    {
      "card_id": "card_01jz8k2m",
      "issue": "用户偏好什么回答风格?",
      "position": {
        "position_id": "pos_01jzp3nq",
        "claim": "偏简洁,先给结论再展开",
        "scope": "技术问答场景;闲聊不一定适用",
        "credence": 6,
        "up_count": 7, "down_count": 1, "neutral_count": 2
      }
    }
  ]
}
```

- 每张命中卡默认带它**当下用的那个 Position**（现算 credence 最高）。`scope` 一起返回，供注入层拼给 LLM。
- `credence` 是服务端现算的派生值（不是存储字段）。
- 同 session 内已召回过的卡不重复返回（去重，沿用 v3 `recall_log` 机制）。

### 副作用

- 记同 session 去重(沿用 v3 recall_log)。
- **不回写任何 Position 字段**：recall / read 不进存储,相关性只在召回时由检索现算(理由见 [`../../works/v4/card.md`](../../works/v4/card.md) §3)。

### 错误

| 情况 | 状态 / 消息 |
|---|---|
| `session_id` 前缀错 / 不存在 | 400 |
| `prompt` 为空 | 400, `prompt required` |
| embedding provider 调用失败 | 500, `embedding failed: <details>` |
