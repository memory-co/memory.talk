# works / trace_push — trace 的写入口和读的参数

## 这个场景在测什么
`POST /works/{id}/trace`:节点把 agent 的记录推上来,和 `GET` 同一个形状(`docs/designs/v5/work-node.md §6`、`docs/api/v5/works.md`)。
- **只有节点能写**:从中心给节点开的 unix socket 上来的请求(测试里是 `TestClient(NodeSocket(app))`,和 `serve.py` 一样)身份是节点,
  只能碰 `/api/works/{id}/trace`;登录的人 POST → 403;
- 推上去的段和点原样读回来(父段、开着的标记、正文、uid);`observedTimeUnixNano` 是中心收到的时刻;
- 默认读不带 agent 那几层和正文;`worklet=` 只看一个工作单元;
- 同一批推两次什么都不变(段 ignored、点 duplicate,变更序号不涨);开着的段合并属性,带终点就结束,结束了的不再动;
- 一批是一个事务:点没有 uid → 422,段也没写;节点写 `work` 段、开 / 普通结束 `worklet` 段、动作点 → 403;别的 work 的工作单元 → 422;
- 节点报 `gone`:现场还活着的不收;收了就结束 worklet 段(status Unset,带当时在哪一列),里面开着的 agent 段跟着结束;
- `cursors` 随批存、`fields=cursors&worklet=` 读回(同一份来源覆盖;不带 worklet → 422);
- `after=<seq>` 只给之后写的或改过的(新点、刚结束的段),`seq` 往前走;`wait` 有新东西马上回来、没有就等到超时,
  这次读不会读到的变化(默认读不带的 agent 段)不叫醒它;
- 没有节点来 flush 的时候关掉工作单元,开着的 agent 段跟着 worklet 段结束(`detached`,终点取它最后一次动静)。

## 不在这测什么
- 节点怎么读 Claude Code、怎么切轮次 → `node/claude`;节点怎么推、重试、收尾 → `node/push`
- claude:// 开现场、和节点连起来的整条路 → `work_servers/claude_worklet`

## fixture 来源
`client`、`svc`、`H`;bash 工作单元(真 tmux,`needs_tmux`)提供一段开着的 worklet 段;推的文档用 `memorytalk.node.otlp` 拼(和节点一样)。
