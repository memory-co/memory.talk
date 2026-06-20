# upgrade

**v4 与 v3 一致** —— `memory.talk upgrade` 升级已安装的实例(拉新版本 / 迁移),行为、参数、流程**完全照 v3**,本目录不复制。

```bash
memory.talk upgrade
```

**v4 唯一变化**:无。`upgrade` 是纯沿用的基础设施(本地维护命令,不涉及 `/v3`→`/v4` 端点切换)。

> 完整契约(升级流程、幂等 / 回滚、迁移注意事项)见 [`../v3/upgrade.md`](../v3/upgrade.md)。v3→v4 的卡数据改名 / 迁移(老卡整体改名 `insight`)另见 [`../../works/v4/card.md`](../../works/v4/card.md) §9。
