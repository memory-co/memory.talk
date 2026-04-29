# memory.talk

> 给 AI agent 跨会话的持久记忆

memory.talk 把你跟 Claude Code、Codex 等 AI 平台的对话历史压缩成**可搜索的认知卡片**(Talk-Card),让下一次会话能"想起"之前的决定、踩过的坑、架构选型。本地存储,零配置启动,可插拔到 Qdrant / PostgreSQL 等后端。

[English](README-EN.md) · [CLI 文档](docs/cli/v2/README.md)

---

## 它解决什么问题

你每次开新会话都要给 AI 复述项目背景、再次走过同样的弯路 —— 因为每次会话都是空白。memory.talk 让这个过程变成:

1. **导入**过去的会话(`memory-talk sync`)
2. **提炼**对话成 cards(LLM 通过 `card` 命令落地)
3. AI 启动时 hook **自动召回**相关记忆(`recall`)
4. AI 思考过程中**主动检索**(`search`)

不是又一个 RAG 库 —— memory.talk 把 retrieval 拆成"无意识召回"和"有意识检索"两种正交的语义。

## 快速开始

### 安装

```bash
pip install memorytalk
```

或从源码:

```bash
git clone https://github.com/memory-co/memory.talk.git
cd memory.talk
pip install -e .
```

### 初始化

```bash
memory-talk setup
```

交互式 wizard 会问你 embedding provider(`local` / `openai`)、port、向量库、关系库等,自动写 `~/.memory-talk/settings.json`,可选立刻启动后台服务,顺便建一个 `memory.talk` 软链(等价于 `memory-talk`)。

> setup 可重复跑 —— 第二次会进"修改模式",每个字段默认就是当前值,Enter 跳过,改了就询问是否重启服务。

### 跑起来

```bash
# 从 Claude Code / Codex 平台导入历史会话
memory-talk sync

# 搜索一下
memory-talk search "LanceDB 选型"

# 读一条 card 详情
memory-talk view card_01jz8k2m

# 看一条 session 的生命周期事件
memory-talk log sess_xxx
```

完整命令列表 → [docs/cli/v2/](docs/cli/v2/README.md)

---

## 核心概念

### Talk-Card

一张压缩的认知单元(≤1024 tokens),由 LLM 从 session 的特定 round 中提炼:

- **Summary** —— 一句话,作为 embedding 锚点
- **Rounds** —— 关键决策 / 推理片段
- **Links** —— 跟其它 cards / sessions 的语义关联
- **Default Link** —— 每张 card 自动跟它的来源 session 关联,生死跟随 card

> cards 是"已经想过的东西",sessions 是"原始对话"。

### Search vs Recall

| | `search` | `recall` |
|---|---|---|
| 触发 | AI 思考时主动调用 | harness hook 自动调用 |
| 意识形态 | 有意识 / 决定要查 | 无意识 / 看到 prompt 即浮现 |
| 输出 | 完整结构(snippets / links / tags) | 极简(`memory-talk view <id>  # summary`) |
| 去重 | 无 | 同 session 已召回过的不再返回 |

底层都建在 **hybrid FTS + 向量** 之上(LanceDB)。

### 存储布局

```
~/.memory-talk/
├── settings.json
├── sessions/<source>/<bucket>/<sess_id>/
│   ├── meta.json
│   ├── rounds.jsonl              # 对话流(append-only)
│   └── events.jsonl              # 生命周期事件
├── cards/<bucket>/<card_id>/
│   ├── card.json
│   └── events.jsonl
├── links/<bucket>/<link_id>.json
├── vectors/                       # LanceDB
├── memory.db                      # SQLite(派生索引)
└── logs/search/<UTC-day>.jsonl
```

**文件层是 source of truth**,SQLite + LanceDB 都是从文件可重建的派生索引。`memory-talk rebuild` 随时可以从文件重建出全部索引。

---

## 输出格式

CLI 默认输出 **Markdown**,运行时按 stdout 是否 TTY 自动决定渲染:

- TTY 终端 → 用 `rich` 渲染成带样式的输出
- 管道 / 脚本 / LLM 消费 → 原始 Markdown(LLM 训练里 Markdown 本就是常见格式)
- `--json` → 结构化 JSON,机器友好

错误也跟着走:Markdown 模式 `**error:** <msg>` 写到 stderr,JSON 模式写到 stdout。

---

## 设计原则

- **Python 不调 LLM**:数据层只做 CRUD / embedding / 向量检索,不做认知。LLM 通过 CLI 调用,认知发生在外部。
- **可插拔的 storage 抽象**:`provider/storage.py` 定义统一原语(write/read/append/list/delete),local-fs 是当前实现,后续可加 S3。Domain ops(write_session_meta 等)在 `repository/<domain>.py` 里调原语,不直接 open 文件。
- **rebuild 永远可行**:任何时候删掉 `memory.db` + `vectors/` 跑 `memory-talk rebuild`,从文件层完整还原。
- **rebuild 期间 server 进入维护模式**:除了 `/v2/status`,所有 API 503 拦掉,避免读到撕裂的中间态。

---

## 命令一览

| 命令 | 用途 |
|---|---|
| [`setup`](docs/cli/v2/setup.md) | 交互式安装 / 改配置 / 重启 |
| [`sync`](docs/cli/v2/sync.md) | 从 Claude Code 等平台导入 session |
| [`search`](docs/cli/v2/search.md) | 有意识检索(混合 FTS + 向量) |
| [`recall`](docs/cli/v2/recall.md) | hook 自动召回(极简形式) |
| [`view`](docs/cli/v2/view.md) | 读单条 card / session |
| [`log`](docs/cli/v2/log.md) | 看对象生命周期事件流 |
| [`card`](docs/cli/v2/card.md) | 创建 card |
| [`tag`](docs/cli/v2/tag.md) | 给 session 打 tag |
| [`link`](docs/cli/v2/link.md) | 写用户 link |
| [`server`](docs/cli/v2/server.md) | 管理本地 API 服务 |
| [`rebuild`](docs/cli/v2/rebuild.md) | 从文件层重建索引 |

---

## 开发

```bash
pip install -e ".[dev]"
pytest memorytalk/tests/
```

跑搜索质量回归(用真 DashScope embedding):

```bash
export QWEN_KEY=sk-...
pytest memorytalk/tests/search/
```

测试套结构:

```
memorytalk/tests/
├── api/            # FastAPI TestClient
├── cli/            # 真 CLI(ASGI 路由 + subprocess)
├── service/        # 服务层(真 SQLite + LanceDB + dummy embedder)
├── provider/       # storage / embedding 原语
├── config/         # Config 加载 + 校验
├── util/           # dsl / ids / snippet / ttl
└── search/         # 搜索质量回归(5 档评分:Excellent/Acceptable/Marginal/Degraded/Failed)
```

184+ 个测试,场景化目录(每个测试用例一个目录,带自己的 README + test.py)。详见 [tests/](memorytalk/tests/)。

---

## License

[Apache License 2.0](LICENSE)
