# work_servers / bash_record — bash 的每条命令进 trace

## 这个场景在测什么
`bash://<目录>` 新起的 bash 带着 `--rcfile`(先读用户的 ~/.bashrc,再装上记命令的钩子),节点读它的命令事件推进 trace
(`docs/designs/v5/work-server-io.md §6`):
- 从记录里送进去的一条命令 = 一轮:人那句是命令,回复是它的输出,轮次带退出码,也带上送它的那次 input id;会话段是这个 bash;
- 失败的命令留着退出码和报错;
- 命令在跑时状态是 busy:再送字 → 409 busy;按 Ctrl-C 不门控,这一轮退出码 130、记成 cancelled;
- 关掉工作单元:节点先 flush,还在跑的命令和会话段按 detached 结束,节点目录删掉;
- `bash:///<脚本>` 是跑脚本,不记(没有 `trace.agent`,也不让节点盯);装钩子之前就起的老现场不假装有记录。

## 不在这测什么
- 节点怎么把事件切成段和点(时间、uid、输出截断、重读)→ `node/bash`;rcfile 本身在真 tmux 里的各种命令 → 实施时手测过,见设计稿 §6

## fixture 来源
`client`、`svc`、`home`;真 tmux + 真 bash(`needs_tmux`);节点放在测试进程里(`tests/_util.py` 的 `LocalCenter` / `LocalNodes`),
等事件文件里出现新的一行再 `poll()` 一次。
