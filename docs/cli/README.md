# CLI Reference

所有命令输出 JSON，供 LLM 或脚本消费。

```
memory-talk
├── sync                           # 自动同步所有平台会话
├── sessions list / read / mark-built
├── cards create / get / list
├── links create / list / delete   # 管理关联（card↔card, card↔session）
├── recall                         # 向量检索
└── status                         # 统计信息
```

配置文件 `~/.memory-talk/settings.json`，不存在时使用默认值，由 AI 直接读写。详见 [settings.md](../structure/settings.md)。

详细文档见各子命令文件。
