# adapters —— 读各平台的会话记录

agent server 把手的「读 round」那一半:在平台自己的记录目录里找到这个会话的文件,解析成 `Round{id, timestamp, role, text}`。每个平台一个文件,实现同一个接口:

| 文件 | 平台 | 找文件 | 解析 |
|---|---|---|---|
| `base.py` | — | `TranscriptAdapter` Protocol:`find(cwd, since_mtime) -> Path | None`(按工作目录和会话开始时间定位记录文件)/ `rounds(path) -> list[Round]` | |
| `claude_code.py` | Claude Code | `~/.claude/projects/<cwd 编码>/<session>.jsonl`(`_project_dir`) | `_text_of` 拼消息正文,`_role` 分 human / assistant / tool |
| `codex.py` | Codex CLI | `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`,`_session_cwd` 从 session_meta 读 cwd 匹配 | |
| `kimi.py` | Kimi Code CLI | `~/.kimi-code/sessions/wd_*/session_<uuid>/`,`_state` 读 state.json 匹配 cwd | 解析 `agents/main/wire.jsonl` |

记录根目录来自 `RuntimeConfig`(`MEMORY_TALK_CLAUDE_PROJECTS` / `MEMORY_TALK_CODEX_SESSIONS` / `MEMORY_TALK_KIMI_SESSIONS`),测试时指到临时目录。
