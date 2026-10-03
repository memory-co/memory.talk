# node / bash — 节点读 bash 的命令事件

## 这个场景在测什么
`memorytalk/node/bash.py`:rcfile 写的事件(start / cmd / done + 每条命令的输出文件)切成段和点(`work-server-io.md §6`):
- 会话段 = 这个 bash(pid),一条命令 = 一轮,人那句 = 命令原文,回复 = 输出(kind `output`,去掉末尾空行);uid / id 由事件在文件里的位置算;
- 退出码记在轮次上,Ctrl-C(130)记成 cancelled;没有输出就没有回复;目录变了另记;状态 idle → busy → idle;
- 前面加空格的命令:原文和输出都不记,只留一个 hidden 的空消息;
- 命令还在跑 = 轮次开着;输出太长留头留尾、中间写省略了多少;输出文件推成功以后才删;
- 换了一个 bash(exec)= 上一个会话 replaced;从游标接着读;flush / 现场没了时开着的都结束。

## 不在这测什么
- 真 bash 怎么写这些事件 → `work_servers/bash_record`

## fixture 来源
`tmp_path` 里的事件文件和输出文件,照 rcfile 写出来的样子造;不起服务、不碰 tmux。
