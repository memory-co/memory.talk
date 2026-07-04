# sync — sync-server 的状态与操作(v5 CLI)

[sync-server](../../works/v5/sync-server.md)(独立摄入服务,一源一 worker)的控制面。**看经验有没有进来、卡在哪、推一把**——不碰记忆本身(那是 query / harness 的事)。

```bash
memory.talk sync status [--json]        # 总览:服务在不在 + 每个 worker 一行
memory.talk sync trigger [<source>]     # 手动触发一轮同步(不给 source = 全部)
memory.talk sync start | stop           # sync-server 进程生命周期
memory.talk sync logs [<source>]        # 尾随日志(排障)
```

## `sync status` 输出形态

```
sync-server: running (pid 4242, up 3d2h)
worker        listen      last push         cursor lag   state
claude-code   fs-watch    2m ago            0            ok
codex         fs-watch    41m ago           0            ok
openclaw      poll/5m     3d ago            2 sessions   backoff (dir missing)
```

- **一 worker 一行**:监听方式、最后推送、游标落差(上游有而库里还没有的量)、状态(ok / backoff / disabled);
- 状态来自 sync-server 自己的 checkpoint(`sync.db`)+ 对 [ingest](../../api/v5/ingest.md) 的最近应答——**worker 之间互不影响**,一个 backoff 别的照跑;
- `--json` 给结构化(hooks / 面板消费)。

## 边界

- `trigger` 只是「现在就跑一轮该源的同步」(冷扫同一条路),**不能改数据**——ingest 是唯一写门,且只有 sync-server 会调它;
- 上游配置(开哪些 worker、路径、poll 间隔)在 sync-server 的声明配置里(works §5 待定),CLI 不塞配置编辑;
- memory daemon 不归它管(`harness status` 顺带报 daemon 健康)。
