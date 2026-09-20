# work

work 树、工作单元(现场)、收件箱、manager、user、召回。对应 [`/api/works`](../../api/v5/works.md)。机制见 [`../../designs/v5/work.md`](../../designs/v5/work.md)。

```
memory.talk work
├── create  --goal '<一句话>' [--parent <work_id>]
├── list    [--root <work_id>] [--created-by <user>] [--all]
├── show    <work_id>
├── set     <work_id> [--goal '<…>'] [--status todo|doing|done|abandoned]
│
├── attach   <work_id> <uri>                      # 打开一个块:协议 → server 建现场
├── worklets <work_id>
├── detach   <work_id> <worklet_id>
├── capture  <work_id> <worklet_id> [--lines 200]
├── rounds   <work_id> <worklet_id>
│
├── inbox    <work_id>
├── manager  <work_id> [--set <work_id> | --unset]
├── users    <work_id>
├── touch    <work_id>
└── servers                                       # 有哪些 work server、各自响应哪些协议
```

## work create

```bash
memory.talk work create --goal '把配置改成环境变量' [--parent work_…]
```

`created_by` = `--user` / `MEMORY_TALK_USER`。输出新 work 的 id、目标、状态(`todo`)。父不存在 → exit 1。

## work list

树,默认只列没结束的(`todo` / `doing`);`--all` 连 `done` / `abandoned` 一起。

```
work_…2f2f  doing  alice  把 v5 做出来
  work_…a1b2  done   alice  实现 issue
  work_…c3d4  doing  bob    实现 work
```

| 参数 | 说明 |
|---|---|
| `--root <id>` | 只看这一棵 |
| `--created-by <user>` | 只看某人建的(`--created-by me` = 当前 `--user`) |
| `--all` | 含已结束的 |

## work show

一个 work 的全貌:目标 / 状态 / 父 / 建者;工作单元(活没活着、窗地址);users(current / history);收件箱最近几条;manager。`--json` 时是各端点的合集。

## work set

改目标 / 状态。`--status done` 要求子 work 全完,否则 exit 1 并列出未完的子 work;结束后工作单元冻结(现场销毁、登记留着)。

## work attach

在 work 里打开一个块。协议在哪个 server 的 `protocols` 里就去哪个,没有就 default(协议名当命令名)。

```bash
memory.talk work attach work_…2f2f codex:///home/alice/memory.talk
memory.talk work attach work_…2f2f bash://
memory.talk work attach work_…2f2f https://localhost:5173/
```

输出:工作单元 id、窗地址(没配 ttyd 时老实打 `窗:无(只有把手)`)、把手能力。已结束的 work → exit 1;命令不在 PATH → exit 1 `cmd_not_found`。

**agent 工作单元的环境里自动带 `MEMORY_TALK_WORK=<work_id>` 和 `MEMORY_TALK_USER=<当前 user>`**——agent 在里面再调 `memory.talk meta …`,提交就挂在这个 user 名下、变动不投回自己。

## work worklets / detach / capture / rounds

| 命令 | 说明 |
|---|---|
| `worklets <id>` | 工作单元清单:id、URI、活没活着、最近重入 |
| `detach <id> <wid>` | 关闭即回收:销毁现场 + 删登记 |
| `capture <id> <wid> [--lines N]` | 抓终端屏幕(`text/plain`);http 工作单元没把手 → exit 1 |
| `rounds <id> <wid>` | agent 工作单元的 round(先从记录文件同步再读);`--json` 给逐 round 标注用 |

## work inbox

收件箱:manager.json 路由过来的变动(meta 对象、子 work 状态),按时间正序,每条:时间、层、路径、动作、谁、从哪路由来。

## work manager

```bash
memory.talk work manager work_…            # 这个 work 的变动打给谁(manager.json,没有则父)
memory.talk work manager work_… --set work_…root
memory.talk work manager work_… --unset    # 回到父
```

## work users / touch

`users`:谁当前在动(current)、谁动过(history),只做可见性不做权限。`touch`:心跳(`--user` 必须有)。

## work servers

`GET /api/works/servers`:这个实例有哪些 work server(bash / claude / codex / kimi / http / default)及各自响应的协议。`work attach <uri>` 时协议去找谁,看这张表;平时几乎不用。
