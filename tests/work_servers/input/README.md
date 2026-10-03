# work_servers / input — 往现场里送字、按键

## 这个场景在测什么
`POST /works/{id}/worklets/{w}/input`(`docs/designs/v5/work-server-io.md §4、§5、§7`):
- 终端类:`text` 逐字打进 tmux 再按回车(真的送到了 shell 里)、`keys` 按键;不收的(bash 的 `paste`、网页的一切)→ 409 `unsupported`;
- 现场不在、work 已归档 → 409 `gone`;`text` 超过 64 KiB → 422;工作单元不存在 → 404;
- 每次送在 trace 里打一个 `worklet.input` 点:谁、input id、哪种、多长、指纹(去掉首尾空白的 sha256),**原文哪儿都没有**;
- agent(claude)按 trace 里最新的 `agent.state` 门控:正在干活 → 409 `busy`,带 `force` 才送;在等确认 → 409 `blocked`;
  按键默认就是 force(能发 Escape 打断它);空闲了照常送,返回送的时候的状态;
- 节点推来的新一轮,第一句人的话和刚送进去的那次对得上(指纹一样、前后 60 秒内),轮次上带 `memorytalk.input.id`;
  在终端窗里手打的那一轮没有。

## 不在这测什么
- 节点怎么读 agent 的记录 → `node/*`;claude 开现场 → `claude_worklet`

## fixture 来源
`client`、`svc`、`home`、`H`;真 tmux(`needs_tmux`);claude 用 PATH 里的假脚本;agent 的状态和轮次由测试当节点推
(`WorkService.write_trace`,就是 `POST /trace` 进的那个写入函数),推的文档用 `memorytalk.node.otlp` 拼。
