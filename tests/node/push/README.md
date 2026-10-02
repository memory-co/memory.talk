# node / push — 节点盯着工作单元,推给中心

## 这个场景在测什么
`memorytalk/node/node.py`(`docs/designs/v5/work-node.md §6、§7`):
- watch 马上读一步,并把「盯着谁」记在 `worklets/<id>/watch.json`;
- 推不成功(中心没起来)游标不动,下一轮从老地方重读,推上去的是同样的 uid;中心拒收(4xx)的那批跳过,不卡住后面;
- 游标随数据一起推(每份来源一行 + reader 的整份状态);节点重启后照 watch.json 接着盯,从中心读回游标接着读;
- flush:读到头、推完,开着的段按原因结束,不再盯;`detached` 连目录一起删,`archived` 留着;
- 现场没了(tmux 会话不在):开着的段按 gone 结束(status Unset),再给 worklet 段补一个 gone 结束;
- 重入开了新的 worklet 段,再 watch 一次,新的会话段挂到新段下;list 报在盯谁、哪些 tmux 会话活着。

## 不在这测什么
- 怎么读 Claude Code → `node/claude`;中心收的规则 → `works/trace_push`

## fixture 来源
假中心(记下每一批、照中心那样存游标,可以让它推不上去或拒收);活着的 tmux 会话由测试给(不碰真 tmux)。
