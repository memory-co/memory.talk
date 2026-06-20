# sync

**v4 与 v3 一致** —— `memory.talk sync start | stop | status` 是后端 watcher,实时把新 session 落库,行为、参数、debounce / cursor 语义**完全照 v3**,本目录不复制。

```bash
memory.talk sync start
memory.talk sync status
memory.talk sync stop
```

**v4 唯一变化**:CLI 打的本地端点从 `/v3/sync*` 挪到 **`/v4/sync*`**(命令用法一字不改;HTTP 契约见 [`../../api/v4/sync.md`](../../api/v4/sync.md))。

> 完整契约(watcher 机制、cursor、endpoints 配置、各子命令行为)见 [`../v3/sync.md`](../v3/sync.md)。
