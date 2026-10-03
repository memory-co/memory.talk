# work_servers / claude_worklet — claude:// 开起来就定身份,output 由节点推进 trace

## 这个场景在测什么
`backend/work_servers/claude.py` + 节点(`docs/designs/v5/work-node.md §5、§7`):
- 新起的 claude 带 `--session-id <uuid>` 和 `--settings <hooks 文件>`(几个 hook 都把事件追加到节点目录里这个工作单元的 hooks.jsonl);
  会话 id 记在登记上、不对外;把手能力是 `input.text` + `input.keys` + `trace.agent`,旧的 rounds 接口对它是空的;
- 取回还活着的现场不重新起 claude;现场死了再重入,新起的 claude 是新的会话 id,登记跟着换;
- hook 脚本:一个事件一行、带收到的时刻,stdout 什么都不写;
- 开起来就让节点盯着(挂在这个工作单元开着的 worklet 段下);claude 写的会话记录和 hooks 进了 trace(会话 → 轮次,消息带正文,token);
- 关掉 / 归档先让节点 flush(会话段按 detached / archived 结束,关掉的连节点目录一起删);现场自己没了节点报 gone;
  gone 之后重入,节点改挂到新的 worklet 段;中心起来时对一遍,活着的现场都让节点盯上。

## 不在这测什么
- 节点怎么切、怎么推 → `node/claude`、`node/push`;中心收的规则 → `works/trace_push`

## fixture 来源
`client`、`svc`、`home`、`H`;PATH 里的假 `claude`(把参数记下来,一直跑着);真 tmux(`needs_tmux`);
节点放在测试进程里(`tests/_util.py` 的 `LocalCenter` / `LocalNodes`:中心和节点直接调对方,不走 socket)。
