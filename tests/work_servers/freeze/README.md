# work_servers / freeze — work 结束,现场销毁、登记留着

## 这个场景在测什么
work 变成 done 之后:所有会话的 tmux 现场被销毁,`sessions` 清单里还在但 `alive: false`;事件里有 `frozen`。

## fixture 来源
`client`、真 tmux(`needs_tmux`)。
