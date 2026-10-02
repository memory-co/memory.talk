"""节点:现场和采集住在边上,往中心推(docs/designs/v5/work-node.md)。

每台机器一个节点进程。中心让它盯着哪个工作单元(watch),它就读那个 agent 的会话记录、收 agent 的 hooks、
看 tmux 现场活没活着,把这些变成 trace(会话 / 轮次 / 工具段,消息点,状态点)推给中心:
POST /api/works/{id}/trace,和读的 GET 同一个形状;推到哪了随同一个请求存进中心(cursors),重启从那里接着读。
中心只管存、查和做决定,不认识任何 agent 的格式;各家的格式和「一轮怎么切」都在这里。

这个包不依赖 backend:以后节点可以在别的机器上跑。现在只有 Claude Code 走这条路(claude.py);
Codex / Kimi 还是中心去拉(旧路径),等这里能解析它们再搬过来。
"""
