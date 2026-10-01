# adapters / claude_code — agent 把手读 Claude Code 的会话记录

## 这个场景在测什么
`claude://<cwd>` 的工作单元是终端 + 把手多一项 `rounds`:按 cwd 编码定位 `~/.claude/projects/<cwd>/*.jsonl`,
只认成员创建之后出现的记录;user / assistant 消息解析成 round(tool_result → tool,isMeta → system,sidechain 跳过);
`GET …/rounds` 先同步再读,存在 worktrace.db 的 `rounds` 表:只追加、按 uuid 去重、增量追加。

同步进来新 round 时切成 `agent.turn` 段(`docs/designs/v5/work-trace.md §2`):挂在 worklet 段下,id 由第一条 round 算,
`memorytalk.round.first / last / count`、`gen_ai.system = anthropic`,不记人;后面有人的输入就结束(终点 = 这一轮最后一条 round),
最后一轮开着;再同步按第一条 round 原地改,不重复;关掉 / 归档之前最后收一次 round,开着的轮次跟着 worklet 段结束
(现场自己没了的,status 和 worklet 段一样是 Unset);归档了的 work 里再关掉工作单元不再收 round——同一目录里后来的别的会话不会混进冻住的 round 和轮次。

## 不在这测什么
- Codex / Kimi 的格式 → 各自场景
- 怎么切、各家时刻怎么解 → `turns`

## fixture 来源
`client`、`home`、`svc`、`H`;PATH 里放一个假 `claude`(只要 tmux 能起);`needs_tmux`。轨迹用 `tests/_util.py` 的 `trace()` 拍平了看。
