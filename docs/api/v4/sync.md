# Sync API

**v4 与 v3 一致** —— 控制后端 watcher(start / stop / status)的接口形态、请求 / 响应体**完全照 v3**,本目录不复制。

**v4 唯一变化**:所有 `/v3/sync*` 路由挪到 **`/v4/sync*`** 前缀,行为不变。

> 完整契约(watcher 机制、debounce、endpoints 配置、各端点请求 / 响应)见 [`../v3/sync.md`](../v3/sync.md)。CLI 用法见 [`../../cli/v4/sync.md`](../../cli/v4/sync.md)。
