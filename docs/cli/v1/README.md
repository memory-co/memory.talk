# CLI Reference

所有命令支持两种输出格式：

- **JSON**（默认）：供 LLM 或脚本消费，中文直接输出（`ensure_ascii=False`）
- **Text**：供人类阅读，`--format text` 或 `-f text`

```bash
memory-talk server status              # JSON 输出（默认）
memory-talk server status -f text      # 人类可读输出
```

```
memory-talk
├── server start / stop / status   # 管理本地 API 服务（status 含数据统计）
├── sync                           # 自动同步所有平台会话
├── session list / read / tag
├── card create / get / list
├── link create / list             # 管理关联（TTL 通过 card get --link-id 自动刷新）
├── recall                         # 纯向量检索（只返回 card）
├── search                         # FTS + 向量 hybrid + 元数据 DSL（同时返回 card / session）
└── rebuild                        # 从文件重建索引
```

配置文件 `~/.memory-talk/settings.json`，不存在时使用默认值，由 AI 直接读写。详见 [settings.md](../../structure/v1/settings.md)。

详细文档见各子命令文件。
