# settings.json

配置文件路径:**`~/.memory-talk/settings.json`**(v3 data root **固定** 在 `~/.memory-talk`,不开 `--data-root` 参数;详见 [`../../cli/v3/setup.md`](../../cli/v3/setup.md))。

不存在时退到内置默认值。**setup wizard** 是首要写入路径(交互式 prompt + 原子写),手工编辑也允许 —— 改完重启 server 生效。

## Schema

```json
{
  "server": {
    "port": 7788
  },
  "vector": {
    "provider": "lancedb"
  },
  "relation": {
    "provider": "sqlite"
  },
  "embedding": {
    "provider": "openai",
    "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
    "auth_key": "${QWEN_KEY}",
    "model": "text-embedding-v4",
    "dim": 1024,
    "timeout": 30.0
  },
  "search": {
    "default_top_k": 10,
    "search_log_retention_days": 0,
    "ranking_formula": "relevance + 0.1 * (review_up - review_down) + 0.02 * log(read_count + 1) - 0.005 * age_days",
    "snippet_head_chars": 100
  },
  "sync": {
    "debounce_ms": 200
  },
  "explore": {
    "cwd": "~/.memory-talk/explore",
    "auto_default_limit": 5
  }
}
```

## 各小节字段

### server

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `port` | integer | `7788` | API 服务监听端口 |

### vector

| 字段 | 类型 | 默认 | 可选 | 说明 |
|---|---|---|---|---|
| `provider` | string | `lancedb` | `lancedb`(目前唯一) | 向量库后端 |

### relation

| 字段 | 类型 | 默认 | 可选 | 说明 |
|---|---|---|---|---|
| `provider` | string | `sqlite` | `sqlite`(目前唯一) | 关系库后端 |

### embedding

| 字段 | 类型 | 默认 | 可选 | 说明 |
|---|---|---|---|---|
| `provider` | string | `local` | `local` / `openai` / `dummy` | Embedding 后端。`dummy` 仅服务测试,setup 不暴露 |
| `model` | string | `all-MiniLM-L6-v2` | 任意 | `local` 时为 sentence-transformers 模型;`openai` 时为远端模型 id |
| `endpoint` | string? | null | OpenAI 兼容 `/v1/embeddings` URL | 仅 `openai` 用 |
| `auth_key` | string? | null | 字面值或 `${VAR}` | 仅 `openai` 用。`${VAR}` 由 `string.Template.substitute` 渲染 |
| `dim` | integer | `384` | 正整数 | 向量维度,**必须**与 provider 实际输出一致 |
| `timeout` | float | `30.0` | 秒 | 仅 `openai` 用 |

> **dim 改了会触发 setup 重算所有 card 的 embedding** —— 详见 [`../../cli/v3/setup.md`](../../cli/v3/setup.md)。

### search

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `default_top_k` | integer | `10` | search 默认 top_k |
| `search_log_retention_days` | integer | `0` | `search_log` 老化阈值(天)。`0` = 永不老化 |
| `ranking_formula` | string | 见下面 | 沉浮公式,详见 [#ranking_formula](#ranking_formula) |
| `snippet_head_chars` | integer | `100` | `hits[].text` 显示预算字符数。有 query token 命中走 keyword window;无命中走头 N 字符预览。详见 [`search-result.md#hit-text-snippet-规则`](../../structure/v3/search-result.md#hit-text-snippet-规则) |

#### ranking_formula

默认值:

```
relevance + 0.1 * (review_up - review_down) + 0.02 * log(read_count + 1) - 0.005 * age_days
```

**可用变量**(给公式用):

| 变量 | 来源 | session 桶是否有 |
|---|---|---|
| `relevance` | hybrid(FTS + 向量)RRF 相关度分 | 有(0 ~ 1) |
| `review_up` | `card.stats.review_up` | 无(置 0) |
| `review_down` | `card.stats.review_down` | 无(置 0) |
| `review_neutral` | `card.stats.review_neutral` | 无(置 0) |
| `review_count` | `card.stats.review_count` | 无(置 0) |
| `read_count` | `card.stats.read_count` | 无(置 0) |
| `recall_count` | `card.stats.recall_count` | 无(置 0) |
| `age_days` | 距 `created_at` 的天数 | 有 |

**可用函数**:`log` / `pow` / `min` / `max` / `abs` 等数学基本函数。后端用安全表达式解析器(白名单 AST),不调 `eval`。

**典型变体**:

```python
# 纯按相关度,忽略论坛信号
"relevance"

# 纯 Reddit hot(忽略 relevance,纯靠 score + age 衰减)
"(review_up - review_down) / pow(age_days + 2, 1.5)"

# 偏向新 + 高争议
"relevance + 0.05 * (review_up + review_down) - 0.01 * age_days"
```

公式**只走 settings,不进 CLI 参数** —— 论坛动力学是系统级偏好,不该每次 search 都重调。

### sync

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `debounce_ms` | integer | `200` | watcher 合并同文件连续写的窗口(毫秒) |

> sync 是否启用的开关**不在 settings.json**,而是在独立的 `~/.memory-talk/sync_state.json` 里持久化(详见 [`../../cli/v3/sync.md`](../../cli/v3/sync.md))—— 它是 runtime 状态而非配置。

### explore

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `cwd` | string | `~/.memory-talk/explore` | claude 启动目录;backend 按这个前缀判断 `metadata.cwd` 是否落在 explore namespace |
| `auto_default_limit` | integer | `5` | `explore auto` 不传 `--limit` 时的默认上限 |

## 跟 v2 的差异

| | v2 | v3 |
|---|---|---|
| `ttl.card.*` | initial / factor / max | **全删** —— 沉浮靠 review + 时间,不依赖 TTL |
| `ttl.link.*` | initial / factor / max | **全删** —— v3 无 link |
| `search.comment_max_length` | 500 | **删** —— link 的 comment 没了;review 的 comment 不设硬上限 |
| `search.ranking_formula` | 无 | **新增** —— 沉浮公式 |
| `sync.debounce_ms` | 无 | **新增** —— watcher 防抖窗口 |
| `explore.cwd` | 在(但 v3 流程不同) | 在,namespace 判断字段从 tag 改为 `metadata.cwd` 前缀 |
| `explore.auto_default_limit` | 无 | **新增** |

## 配置变更生效

- **运行时不重读**:server 在 lifespan 启动时读一次 settings,后续运行不重读
- **改完要重启** server 才生效。setup wizard 改完会**询问是否立即重启**
- **dim 改了**:setup 同步触发 embedding 重算(就地刷向量库),不需要单独命令
