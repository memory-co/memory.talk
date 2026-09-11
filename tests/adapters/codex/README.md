# adapters / codex — 读 Codex 的 rollout 记录

## 这个场景在测什么
`CodexAdapter`:按 `session_meta.cwd` 匹配工作目录找到 `rollout-*.jsonl`;`user_message` / `agent_message` / `function_call` /
`function_call_output` 解析成 round,`task_started` 之类的控制事件跳过。纯解析,不起 tmux。

## fixture 来源
`home`(临时的 codex 记录根)。
