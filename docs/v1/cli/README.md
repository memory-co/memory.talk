# CLI Reference

所有命令输出 JSON，供 LLM 或脚本消费。

```
memory-talk
├── setup                          # 一次性初始化
├── sync                           # 自动同步所有平台会话
├── sessions list / read / mark-built
├── cards create / get / list / links
├── links create                   # 为已有 card 补建关联
├── recall                         # 向量检索
├── raw read                       # 读原始 rounds
└── status                         # 统计信息
```

全局选项 `--data-root PATH` 覆盖默认数据目录 `~/.memory-talk`。

默认配置文件路径 `~/.memory-talk/settings.json`。

详细文档见各子命令文件。
