# node / claude — 节点读 Claude Code 的会话记录和 hooks

## 这个场景在测什么
`memorytalk/node/claude.py`:把会话记录(`<projects>/*/<会话 id>.jsonl`)和 hooks 事件文件按时刻合着读,切成段和点
(`docs/designs/v5/work-trace.md §2、§5`)。记录和 hook 事件照 Claude Code 2.1 真实记录的样子造。
- 一轮 = 人的一条输入到 Stop hook:轮次段 id 由那条输入的 uid 算,挂在会话段下;工具段由调用 id 算,挂在轮次下,结果回来结束;
- 每条消息一个点,uid = `<worklet>:<uuid>[:<第几块>]`,正文在 body;状态点跟着 hooks 走(idle / busy / blocked);
- 没有 hooks:看到第一条记录开会话段,`stop_reason = end_turn` 收一轮;有 hooks:end_turn 不算,等 Stop 或 `turn_duration`;
- Esc(`[Request interrupted…`)= 这一轮和开着的工具 cancelled;`/clear` = 上一个会话 replaced、新会话(记录比 hook 先到也只开一段);
- 给前一句的 Stop 不结束下一轮;人又说了一句,上一轮按它自己最后一条记录收;出错的工具调用 status Error;
- token 按 API 消息(message.id)算一次再加总;后台任务回来触发的一轮是系统发起的(role system,`memorytalk.turn.origin`);
- 从中心存的游标接着读(节点重启):不重复、轮次接得上;半行等写完再读;不认识的记录类型计数;子 agent 的行跳过;
- flush 时开着的段按原因结束;很长的记录分几批推完。

## 不在这测什么
- 推、重试、现场没了 → `node/push`;中心怎么收 → `works/trace_push`

## fixture 来源
`tmp_path` 里的假 projects 目录和 hooks 文件;不起服务、不碰 tmux。
