# CLI Reference (v2)

v2 的设计中心是 **search**——所有读取都以一次 search 为起点。v2 不再发行 result_id 这类追踪 token——search 直接返回带前缀的裸 id（`card_<ULID>` / `sess_<ULID>` / `link_<ULID>`），调用方拿到之后直接喂给 `view` / `log` / `tag` / `link create`。"这次 AI 会话最终用了哪些数据" 由 AI session 自己的 tool-use 对话天然记录——sync 之后就能完整复原，服务端不再造一份追踪包装。

v2 是通过环境变量切换的 CLI 版本：

```bash
MEMORY_TALK_CLI_VERSION=v2 memory-talk --help
```

不设置该变量时默认为 v1。

## 命令树

```
memory-talk
├── search <query> [--where DSL] [--top-k N]  # 有意识检索:AI 主动查记忆
├── recall <session_id> <prompt>              # 无意识召回:hook 阶段自动注入 top-K 极简 cards
├── view <id>                                 # 读取 card 或 session（按 id 前缀自动判型）
├── log <id>                                  # 查一个 card / session 的全生命周期事件
├── card <json>                               # 创建 card
├── tag
│   ├── add <session_id> <tag ...>            # 给 session 加 tag
│   └── remove <session_id> <tag ...>         # 去掉 tag
├── link create <json>                        # 写入用户 link
├── sync [--data-root PATH]                   # 从平台本地文件导入 session
├── rebuild                                   # 阻塞式重建索引
└── server start | stop | status              # 管理本地 API 服务
```

对比 v1，v2 **不再包含**：v1 的旧 `recall`(语义跟 search 重合的另一种主动查询)、`session`（整个子命令树下线）、`card read` / `card get / list`、`link list`。读取一律走 `search` → `view <id>`；card / session 共用同一个读取入口，按前缀自动判型。tag 从 v1 的 `session tag` 提升为一级命令，依然只作用于 session。

v2 的 `search` 和 `recall` 都是 AI 触发的,差别在**意识形态**:

- **`search` = 有意识检索**:AI 在思考过程中主动决定"我要查一下记忆",带具体 query 和过滤条件。返回完整结构(snippets / links / tags / source 等)供 AI 推理。
- **`recall` = 无意识召回**:在 harness hook 阶段被自动调用,把当前 user prompt 喂给 recall,服务端从记忆库里挑 top-K 最相关的 cards,以**极简**(只 id + summary)形式注入 LLM context,模拟"看到 prompt 时脑子里浮现的相关记忆"。带 `session_id` 用于跨多次召回去重。

详见 [search.md](search.md) 与 [recall.md](recall.md)。两者建在同一套 hybrid FTS+vector 检索基础上。

## ID 前缀约定

v2 所有对外的主键都带类型前缀：

| 对象 | 前缀 | 示例 |
|------|------|------|
| Card | `card_` | `card_01jz8k2m0000000000000000` |
| Session | `sess_` | `sess_187c6576_875f_4e3e_8fd8` |
| Link | `link_` | `link_01jzq7rm0000000000000000` |

前缀让 `view <id>` / `log <id>` 一眼判型。链接两端的对象（`source_id` / `target_id` / `links[].target_id`）也一律前缀化。

**没有 result_id，没有 TTL 授权凭据**——id 本身就是合法的读取凭据。服务端做存在性校验，过期的对象（`ttl < 0`）读取时会提示。

## 输出格式

所有命令支持两种输出，**默认是 Markdown**：

- **Markdown（默认）**:CLI 直接产出 Markdown 文本。运行时按 `sys.stdout.isatty()` 决定渲染:
  - **TTY（人在看）**:用 Markdown 渲染器(rich 之类)直接渲染成带样式的输出。
  - **非 TTY（pipe / script / LLM）**:原样输出 raw Markdown。LLM 训练里 Markdown 本身就是常见格式,直接喂给它就能消化。
- **JSON**:加 `--json`。机器消费的结构化形态,永远 stdout,UTF-8 直出(`ensure_ascii=False`)。

```bash
memory-talk view card_01jz8k2m            # TTY → 渲染后的 Markdown
memory-talk view card_01jz8k2m | cat      # 非 TTY → 原始 Markdown
memory-talk view card_01jz8k2m --json     # JSON
```

错误也走同一契约:

| 模式 | 成功 | 失败 |
|------|------|------|
| Markdown(默认)| Markdown 到 stdout | `**error:** <message>` Markdown 到 **stderr**,exit 1 |
| `--json` | JSON 到 stdout | `{"error": "..."}` 到 **stdout**,exit 1 |

下面各子命令文档里的"Markdown 输出"示例是**未经渲染的 raw Markdown** ——也就是非 TTY / pipe 场景下你真正会拿到的字符串。在终端里看到的会是被渲染过的形态。

配置文件 `~/.memory-talk/settings.json`,不存在时使用默认值。详见 [settings.md](../../structure/v2/settings.md)。

详细文档见各子命令文件。search 的输出形态和审计落库见 [search-result.md](../../structure/v2/search-result.md)。
