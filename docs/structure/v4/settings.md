# settings.json

配置文件路径:**`~/.memory.talk/settings.json`**(data root **固定** 在 `~/.memory.talk`,不开 `--data-root` 参数;详见 [`../../cli/v4/setup.md`](../../cli/v4/setup.md))。

不存在时退到内置默认值。**setup wizard** 是首要写入路径(交互式 prompt + 原子写),手工编辑也允许 —— 改完重启 server 生效。

> schema、各段(`server` / `vector` / `relation` / `embedding` / `search` / `sync` / `explore`)、wizard 写入 / 手工编辑语义**沿用 v3**;v4 唯一差异是 LanceDB 多了两个向量 collection(`cards` / `positions`,见末尾「v4 向量 collections」),配置段本身不变。

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
    "snippet_head_chars": 100
  },
  "sync": {
    "enabled": true,
    "debounce_ms": 200,
    "endpoints": null
  },
  "explore": {
    "cwd": "~/.memory.talk/explore",
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
| `batch_size` | integer | `10` | 正整数 | embedder 一次 POST 多少条 `input`。DashScope OpenAI-compatible **硬上限 10**(超了静默 400),OpenAI 真品官方限 2048,vLLM 看部署。`local` / `dummy` 忽略此字段。改了立即生效(server 重启) |

> **dim 改了会触发 setup 重算所有 embedding** —— 详见 [`../../cli/v4/setup.md`](../../cli/v4/setup.md);v4 下重算覆盖全部 collection(含新增的 `cards` / `positions`)。

### search

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `default_top_k` | integer | `10` | search 默认 top_k |
| `search_log_retention_days` | integer | `0` | `search_log` 老化阈值(天)。`0` = 永不老化 |
| `snippet_head_chars` | integer | `100` | snippet 显示预算字符数。有 query token 命中走 keyword window;无命中走头 N 字符预览 |

> **v4 没有 `ranking_formula`**:v3 那条沉浮公式(吃 `review_up/down` + `read_count` + `age_days`)在 v4 整套删掉 —— search 排序只走检索相关性,卡的「当下答案」由现算 credence 决定,不存在可配置的论坛公式。搜索结果形态见 [`search-result.md`](search-result.md)。

### sync

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `enabled` | boolean | `true` | watcher 是否启用 |
| `debounce_ms` | integer | `200` | watcher 合并同文件连续写的窗口(毫秒) |
| `endpoints` | `EndpointConfig[]?` | `null` | **null = 自动检测**(所有 `DEFAULT_LOCATION` 存在的 adapter 起一份);非 null 时**精确取这个清单**,不再自动扫 |

#### `endpoints[]` 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `source` | string | ✓ | 注册过的 adapter 名(`claude-code` / `codex` / `openclaw`) |
| `location` | string | ✓ | 端点定位符 —— 文件型是绝对路径,HTTP 型是 base URL |
| `label` | string? | | 可读别名,用于状态表 / 日志的 `<source>@<label>`;未设回退到 `location` |
| `auth_key` | string? | | HTTP 型 adapter 用;字面值或 `${VAR}` |

`EndpointConfig` 允许附加 adapter 特有 kwargs(`model_config = ConfigDict(extra="allow")`),透传到 `cls(location=..., label=..., **extras)`。

示例(显式配置两个 openclaw endpoint):

```json
"sync": {
  "enabled": true,
  "endpoints": [
    {"source": "claude-code", "location": "~/.claude/projects"},
    {"source": "codex",       "location": "~/.codex/sessions"},
    {"source": "openclaw", "location": "https://us.openclaw.example",
     "label": "us", "auth_key": "${OPENCLAW_US_KEY}"},
    {"source": "openclaw", "location": "https://eu.openclaw.example",
     "label": "eu", "auth_key": "${OPENCLAW_EU_KEY}"}
  ]
}
```

### explore

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `cwd` | string | `~/.memory.talk/explore` | claude 启动目录;backend 按这个前缀判断 `metadata.cwd` 是否落在 explore namespace |
| `auto_default_limit` | integer | `5` | `explore auto` 不传 `--limit` 时的默认上限 |

## 环境变量插值

`auth_key`(以及 `endpoints[].auth_key`)支持 `${VAR}` 形式,由 `string.Template.substitute` 在加载时渲染成环境变量值 —— 密钥不落明文进 `settings.json`。

## 配置变更生效

- **运行时不重读**:server 在 lifespan 启动时读一次 settings,后续运行不重读
- **改完要重启** server 才生效。setup wizard 改完会**询问是否立即重启**
- **dim 改了**:setup 同步触发 embedding 重算(就地刷向量库),不需要单独命令

## v4 向量 collections

v4 的 LanceDB 向量库在 v3 基础上**新增两个 collection**(为问题图检索服务):

| collection | embed 什么 | 来源 |
|---|---|---|
| `insights` | v3 老卡文本 | 沿用 v3(v3 `cards` 改名而来) |
| `rounds` | session 旁白 round | 沿用 v3 |
| `cards` | v4 卡的 `issue`(问题) | **v4 新增** |
| `positions` | v4 答案的 `claim` | **v4 新增** |

这只是 collection 清单的增量;`settings.json` 的 `embedding` / `vector` 配置段本身不变(同一套 provider / model / dim 管所有 collection)。磁盘布局速查见 [`filesystem.md`](filesystem.md)。
