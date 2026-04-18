---
name: using-memory-talk
description: Use when starting any conversation - provides persistent cross-session memory via Talk-Cards
---

# memory.talk

你有持久化的跨会话记忆。过去的对话以 **Talk-Card** 形式保存 —— 一句 `summary` 认知总结、一组压缩后的 `rounds`、以及和其他 card/session 的 `links`。每条 card 和 link 都有 TTL：被访问会续命，冷门会自然淡忘。

## CLI Quick Reference

所有命令走 `Bash` 工具，默认输出 JSON（加 `-f text` 输出人类可读格式）。

```
memory-talk server start                           # 首次启动（自动建 ~/.memory-talk/）
memory-talk server status                          # 运行状态 + 数据统计
memory-talk server stop

memory-talk sync                                   # 扫所有平台，导入新 session（自动去重）

memory-talk session list [--tag TAG]...            # 列 session，可按 tag 筛选（unbuilt / built / claude / project:X）
memory-talk session read <SESSION_ID> [--start N] [--end M]
memory-talk session tag <SESSION_ID> add|remove|list <TAG>...

memory-talk card create '<JSON>'                   # 创建 Talk-Card（自动 embedding）
memory-talk card get <CARD_ID> [--link-id <LINK_ID>]   # 带 --link-id 会刷新 link 的 TTL
memory-talk card list [--session-id <ID>]

memory-talk link create '<JSON>'                   # 跨 card 补 link
memory-talk link list <ID> [--type card|session]   # 查某个 card/session 的所有 link

memory-talk recall "<QUERY>" [--top-k N]           # 向量检索（top-k 默认 5）
memory-talk rebuild                                # 从文件重建索引（换 embedding 后跑一次）
```

配置在 `~/.memory-talk/settings.json`，由 AI 直接读写，schema 见 `docs/structure/settings.md`。

## 数据结构

**Talk-Card**：`{card_id, summary, rounds: [{role, text, thinking?}], links: [{id, type: session|card, comment}], ttl, session_id?, created_at}` —— summary 是 embedding 锚点；rounds 是极度精简的对话，只有角色和文本；links 统一表达关联（包括和来源 session 的关联）。

**Session**：从平台导入的原始对话录像。Round 带完整原始结构（`round_id / parent_id / content block / cwd` 等）。Session 是录像，Card 是记忆。

**Link**：`{link_id, source_id/type, target_id/type, comment, ttl}`。方向由 source→target 表达。Card 创建时内嵌的 link 简写为 `{id, type, comment}`，source 隐含为当前 card。

## 什么时候用哪个子 skill

- **会话开始** / 用户提到过去的工作 → `/recall` 搜索相关记忆。
- **用户要导入对话** → `/explore` 做 `sync`。
- **导入后整理** → `/build` 把 session 精炼成 card。
- **首装或换后端** → `/setup`。

详见各子 skill 的 SKILL.md。
