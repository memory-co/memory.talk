# CLI Reference

所有命令输出 JSON，供 LLM 或脚本消费。

```
memory-talk
├── sync                           # 自动同步所有平台会话
├── sessions list / read / mark-built
├── cards create / get / list / links
├── links create                   # 为已有 card 补建关联
├── recall                         # 向量检索
└── status                         # 统计信息
```

配置文件 `~/.memory-talk/settings.json`，不存在时使用默认值，由 AI 直接读写。详见 [settings.md](settings.md)。

详细文档见各子命令文件。
