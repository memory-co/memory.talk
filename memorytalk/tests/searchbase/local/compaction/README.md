# compaction — Maintenance 子系统的全部职责

## 这个场景在测什么

`Maintenance` class 是 searchbase 的自维护核心 —— 这里覆盖它**除了 EMFILE
反应链以外**的所有行为(EMFILE 那条路有自己的反应 / 锁 / 重连语义,
单独放在 `emfile_recovery/`)。包含:

1. **生命周期**:`start()` / `stop()` 幂等,`stop` 不依赖 `start`
2. **周期循环**:`start()` 启动后立刻跑一次 compaction,之后每
   `compact_interval_seconds` 跳一次
3. **崩溃韧性**:循环里**单次 `compact_all` 失败**不会杀掉循环
   (this is the regression net for the design gap that prompted
   pulling Maintenance out of backend.py into its own class)
4. **错误字段语义**:`last_compact_error` 反映**最近一次**的状态 ——
   失败时记录,**下一次成功时清零**,不残留历史
5. **observability**:`health()` 暴露 6 个字段(3 个 compaction +
   3 个 EMFILE,即使没 EMFILE 也有默认值);counts 跟操作匹配
6. **public health 接口**:`backend.health().detail` 直接转发 Maintenance
   的字段,backend 不二次包装

## 为什么 EMFILE 不在这

EMFILE 是 **search 路径上撞错后通过 Maintenance 反应链回来**的,涉及
generation counter / lock / 重连 / known set 刷新 —— 自成一个测试场景。
放在一起会让两个不同的故事线挤在同一个 README。

## fixture 来源

- `backend` —— 走 backend 公开接口的测试(health、loop 整体看观察)
- `index` —— 直接构造 `Maintenance(index, ...)` 控制 interval,
  细颗粒度地驱动 `compact_all()` / 看错误字段清零
