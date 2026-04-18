---
name: setup
description: Use on first install or when user wants to configure memory.talk storage backends
---

# Setup

memory.talk 没有专门的 setup 命令。首次使用：启动 server，它会自动创建数据目录和默认配置；需要换后端时直接编辑 `~/.memory-talk/settings.json`。

## Steps

### 1. 启动服务

```
memory-talk server start
```

首次运行自动创建 `~/.memory-talk/` 目录结构，写入默认 `settings.json`（零依赖本地配置）。

### 2. 验证

```
memory-talk server status
```

运行中会返回 provider、数据统计；未运行返回 `not_running`。

### 3. （可选）换后端

直接编辑 `~/.memory-talk/settings.json`，改完重启 server。完整 schema 见 `docs/structure/settings.md`。

**默认（零配置）：**

```json
{
  "embedding": {"provider": "dummy", "model": "all-MiniLM-L6-v2"},
  "vector":    {"provider": "lancedb"},
  "relation":  {"provider": "sqlite"}
}
```

**OpenAI 兼容 embedding（例如 Aliyun DashScope）：**

先 `export QWEN_KEY=<your key>`，然后：

```json
{
  "embedding": {
    "provider": "openai",
    "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
    "auth_env_key": "QWEN_KEY",
    "model": "text-embedding-v4",
    "dim": 1024
  }
}
```

切换 provider 后如果已经有老数据，跑一次 `memory-talk rebuild` 用新 embedder 重算向量。
