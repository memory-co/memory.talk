# adapters / claude_code — agent 把手读 Claude Code 的会话记录

## 这个场景在测什么
`claude://<cwd>` 的会话是终端 + 把手多一项 `rounds`:按 cwd 编码定位 `~/.claude/projects/<cwd>/*.jsonl`,
只认成员创建之后出现的记录;user / assistant 消息解析成 round(tool_result → tool,isMeta → system,sidechain 跳过);
`GET …/rounds` 先同步再读,append-only、按 uuid 去重、增量追加。

## 不在这测什么
- Codex / Kimi 的格式 → 各自场景

## fixture 来源
`client`、`home`;PATH 里放一个假 `claude`(只要 tmux 能起);`needs_tmux`。
