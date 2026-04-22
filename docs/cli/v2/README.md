# CLI Reference (v2)

v2 的设计中心是 **search**——所有读取都以一次 search 为起点，拿到 `result_id` 后再调 `view` 读取具体内容。v2 不再暴露按裸 id 读取 card / session / link 的接口，从而让服务端能追踪"这次搜索看了什么、链出到哪里"。

v2 是通过环境变量切换的 CLI 版本：

```bash
MEMORY_TALK_CLI_VERSION=v2 memory-talk --help
```

不设置该变量时默认为 v1。

## 命令树

```
memory-talk
├── search <query> [--where DSL] [--top-k N]  # 主检索入口，返回 result_id 列表
├── view <result_id>                          # 按 search 给出的 result_id 读取 card 或 session
├── log <result_id>                           # 查一个 card / session 的全生命周期事件
├── card <json>                               # 创建 card（返回 card_id 用于日志 / 调试定位）
├── tag
│   ├── add <result_id> <tag ...>             # 给 session 加 tag（只接受 session 类型 result_id）
│   └── remove <result_id> <tag ...>          # 去掉 tag
├── link create <json>                        # 写入关联
├── sync [--data-root PATH]                   # 从平台本地文件导入 session
├── rebuild                                   # 阻塞式重建索引
└── server start | stop | status              # 管理本地 API 服务
```

对比 v1，v2 **不再包含**：`recall`、`session`（整个子命令树下线）、`card read`、`card get / list`、`link list`。读取一律走 `search` → `view <result_id>`，card / session 共用同一个读取入口，按 result_id 前缀自动分发。tag 从 v1 的 `session tag` 提升为一级命令，依然只作用于 session。

## result_id

`result_id` 由 search 产出，形如 `{search_id}.{type}{rank}`：

- `sch_01K7XABC....c1` — 第 1 个 card 结果
- `sch_01K7XABC....s2` — 第 2 个 session 结果

`c` / `s` 前缀决定 `view` 能读出什么形态的内容，也决定哪些命令可用：`tag add/remove` 只接受 `.s<N>`，传入 `.c<N>` 会返回 type mismatch。

result_id 有 TTL（默认 30 天，`settings.search.result_ttl` 可配）。过期后读取返回 expired 错误。

完整的 result_id 形态对照（含 view 现生的 `.l<N>`、log 现生的 `.e<N>`）、生命周期、验证流程见 [structure/v2/search-result.md](../../structure/v2/search-result.md)。

## 输出格式

所有命令支持：

- **JSON**（默认）：供 LLM 或脚本消费，中文直接输出（`ensure_ascii=False`）
- **Text**：`--format text` 或 `-f text`，供人类阅读

```bash
memory-talk server status              # JSON 输出（默认）
memory-talk server status -f text      # 人类可读输出
```

配置文件 `~/.memory-talk/settings.json`，不存在时使用默认值。详见 [settings.md](../../structure/v2/settings.md)。

详细文档见各子命令文件。
