# memory.talk node

本机节点的生命周期([designs work-node.md](../../designs/v5/work-node.md)):读本机 agent 的会话记录、收 agent 的 hooks、看 tmux 现场活没活着,变成 trace 推给中心(`POST /api/works/{id}/trace`,经 `<home>/center.sock`)。现在只有 `claude://` 走这条路。

```
memory.talk node start      # 后台拉起(server start 会顺手起它)
memory.talk node stop
memory.talk node status     [--json]
memory.talk node daemon     # 前台阻塞,日志走 stdout
```

**节点不是中心的子进程**:`server start` 顺手起它、`server stop` 连它一起停;`server restart` 只重启中心,不动它(agent 照跑、记录照读,中心回来了接着推);节点重启也不动 agent——它记着在盯谁(`<home>/node/worklets/<id>/watch.json`),推到哪了存在中心,起来以后从那里接着读。

## start

后台拉起,等它的控制口(`<home>/node/node.sock`)就绪。已经在跑 → 不动,退出码 0。起不来 → 打日志尾巴,退出码 1。

```
节点已启动(pid 12346)
  目录    ~/.memory.talk/node
  日志    ~/.memory.talk/node/node.log
  停止    memory.talk node stop
```

## stop

按 `node.json` 里的 pid 发 SIGTERM,等 5 秒不退再 SIGKILL。不动 agent、不动 tmux 会话。

## status

```
节点运行中(pid 12346)
  目录     ~/.memory.talk/node
  在盯     2 个工作单元
  启动于   2026-10-02T12:10:48Z
```

没在跑 → 退出码 1。

## daemon

前台跑。听 `<home>/node/node.sock`(0600,中心说 watch / flush / list 的口子),每 0.5 秒轮一遍盯着的工作单元:只 stat,变了才读,读到的推给 `<home>/center.sock`。

## 目录

```
<home>/node/
├── node.sock / node.json / node.log
└── worklets/<worklet id>/
    ├── watch.json        盯着它的那份说明(中心给的:work、trace id、挂在哪个 worklet 段下、会话 id、hooks 文件……)
    ├── settings.json     claude --settings:注入的 hooks
    └── hooks.jsonl       hook 事件,一行一个(只追加;关掉工作单元时整个目录删掉)
```
