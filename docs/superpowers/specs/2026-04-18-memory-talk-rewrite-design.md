# memory.talk 完整重写设计

## 概述

基于 docs/ 规格完全重写 memory_talk/ Python 工程。删除现有代码，从零实现。

## 架构

4 层分离：

```
CLI (Click) → HTTP → API (FastAPI) → Service → Storage
```

- **CLI**：用户入口，管控 server 生命周期，所有数据操作通过 HTTP 调 API
- **API**：FastAPI，localhost:7788 守护进程，REST 端点对应 docs/api/
- **Service**：业务逻辑（TTL 计算、embedding、去重），不依赖 HTTP
- **Storage**：SQLite + LanceDB + 文件存储，只做数据存取

## CLI 命令

```
memory-talk
├── server start / stop / status
├── sync
├── sessions list / read / tag
├── cards create / get / list
├── links create / list
├── recall "<query>" [--top-k N]
└── status
```

`sync` 是胶水：读平台文件 → 调 POST /sessions 写入。其余命令 1:1 映射 API。

## API 端点

按 docs/api/ 定义，无增减：

```
POST   /sessions                  导入 session
GET    /sessions                  列出（支持 tag 筛选）
GET    /sessions/:id              读取 rounds（支持 start/end 范围）
POST   /sessions/:id/tags         添加 tags
DELETE /sessions/:id/tags         移除 tags

POST   /cards                     创建 card（自动 embedding + TTL 初始化）
GET    /cards                     列出（支持 session_id 筛选）
GET    /cards/:id                 读取（支持 link_id 参数刷新 link TTL）

POST   /links                     创建 link
GET    /links?id=<ID>             查询关联（支持 type 筛选）
DELETE /links/:link_id            删除（仅人工管理）

POST   /recall                    向量检索（自动刷新 card TTL）

GET    /status                    统计信息
```

## 数据模型

严格按 docs/structure/ 定义：

### Session（docs/structure/session.md）
```
Session {
  session_id, source, created_at, metadata, tags[], rounds[], round_count, synced_at
}

Round {
  round_id, parent_id, timestamp, speaker, role, content[], is_sidechain, cwd, usage?
}

ContentBlock = TextBlock | CodeBlock | ThinkingBlock
```

### TalkCard（docs/structure/talk-card.md）
```
TalkCard {
  card_id (ULID), summary, session_id?, rounds[], links[], ttl, created_at
}

CardRound {
  role, text, thinking?
}
```

### Link（docs/structure/link.md）
```
Link {
  link_id (ULID), source_id, source_type, target_id, target_type, comment?, ttl, created_at
}
```

cards create 时 link 简写为 `{id, type, comment}`，source 隐含为当前 card。

### TTL 机制
- 数据库存 `expires_at` 时间戳
- 读取时计算 `ttl = expires_at - now`（秒）
- 访问刷新：`expires_at = now + min(remaining * factor, max)`
- recall 命中 → 刷新 card TTL
- cards get --link-id → 刷新 link TTL
- ttl <= 0 → 不出现在查询结果中（数据保留）
- factor 和 max 在 settings.json 中分别配置 card 和 link

## 存储

```
~/.memory-talk/
├── settings.json                              # JSON 配置
├── sessions/{source}/{id[0:2]}/{session_id}/
│   ├── meta.json                              # 会话元数据
│   └── rounds.jsonl                           # 原始对话轮次
├── cards/{id[0:2]}/{card_id}.json             # 记忆卡片
├── data/
│   ├── vectors/                               # LanceDB
│   └── relation.db                            # SQLite
└── server.pid                                 # PID 文件
```

### SQLite 表

```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    metadata TEXT,          -- JSON
    tags TEXT,              -- JSON array
    round_count INTEGER,
    synced_at TEXT
);

CREATE TABLE cards (
    card_id TEXT PRIMARY KEY,
    summary TEXT NOT NULL,
    session_id TEXT,         -- 可空，冗余字段
    expires_at REAL NOT NULL,  -- Unix timestamp
    created_at TEXT NOT NULL
);

CREATE TABLE links (
    link_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_type TEXT NOT NULL,   -- 'card' | 'session'
    target_id TEXT NOT NULL,
    target_type TEXT NOT NULL,   -- 'card' | 'session'
    comment TEXT,
    expires_at REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE ingest_log (
    source_path TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    ingested_at TEXT NOT NULL
);
```

## 模块结构

```
memory_talk/
├── __init__.py
├── __main__.py
├── cli.py                     # Click group
├── config.py                  # Settings JSON 读写
├── api/
│   ├── __init__.py            # FastAPI app + lifespan
│   ├── sessions.py
│   ├── cards.py
│   ├── links.py
│   ├── recall.py
│   └── status.py
├── service/
│   ├── __init__.py
│   ├── sessions.py
│   ├── cards.py
│   ├── links.py
│   ├── recall.py
│   └── ttl.py                 # expires_at ↔ ttl 转换、factor 刷新
├── models/
│   ├── __init__.py
│   ├── session.py             # Session, Round, ContentBlock
│   ├── card.py                # TalkCard, CardRound
│   └── link.py                # Link
├── storage/
│   ├── __init__.py
│   ├── sqlite.py
│   ├── lancedb.py
│   ├── files.py               # sessions JSONL + cards JSON 文件存储
│   └── init_db.py             # 建表
├── adapters/
│   ├── __init__.py
│   ├── base.py
│   └── claude_code.py
└── embedding.py
```

## 测试策略

**全部场景测试，不写单元测试。** 每个测试对应 stories/s1/ 中的一个故事。

```
tests/
├── conftest.py                    # 临时 data_root + server fixture
├── test_story_01_database.py      # sync → read → cards create → verify
├── test_story_02_bug.py           # sync → read → cards create with links → verify link
└── test_story_03_recall.py        # recall → links list → cards get --link-id → verify TTL
```

### conftest.py
- `temp_data_root` fixture：临时目录 + settings.json
- `server` fixture：启动 FastAPI TestClient（httpx ASGITransport，不需要真实 HTTP 进程）
- `cli_runner` fixture：Click CliRunner + 注入 data_root
- `fake_claude_sessions` fixture：在临时目录下创建模拟 Claude Code JSONL 文件

### test_story_01_database.py（对应 01-database-decision.md）
1. sync → 导入模拟 session
2. sessions list → 确认导入
3. sessions read → 读出 rounds
4. cards create → 创建精简 card（role/text/thinking）+ link to session
5. recall → 检索到这张 card
6. status → 验证计数

### test_story_02_bug.py（对应 02-bug-investigation.md）
1. sync → 导入 bug 排查 session
2. cards create → 创建 bug card + link to session + link to story01 的 card
3. links list → 验证两条 link
4. cards get → 验证 card 结构

### test_story_03_recall.py（对应 03-recall-and-connect.md）
1. 基于 story01 + story02 已有数据
2. recall "ChromaDB 选型" → 返回 cards + ttl + links
3. cards get --link-id → 验证 link TTL 被刷新
4. 再次 recall → 验证 card TTL 被刷新（expires_at 变大）

## 依赖

```
click>=8.1.0
pydantic>=2.0.0
pyyaml>=6.0.0
fastapi>=0.109.0
uvicorn>=0.27.0
httpx>=0.25.0
lancedb>=0.6.0
numpy>=1.24.0
python-ulid>=2.0.0

[dev]
pytest>=7.4.0
pytest-cov>=4.1.0
```

embedding 默认用 DummyEmbedder（哈希生成固定维度向量），sentence-transformers 作为可选依赖。
