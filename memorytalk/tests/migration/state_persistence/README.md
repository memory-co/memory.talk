# state_persistence

## 测什么

`MigrationState` 对 `migrations_state.json` 的所有交互:

- 文件缺失时 `load()` 返回空 + 查询接口报"没记录"
- `mark()` + `save()` 一来回能持久化,二次 `mark()` 同 (version, subsystem) 是替换而不是堆栈
- `highest_applied()` 按传入的 versions 顺序挑最大
- 坏 JSON / 坏 `applied` 字段都抛 `StateLoadError`(让 runner 把"我搞丢了"上抛成 operator 介入事件,不是悄悄当成 fresh 重跑)
- `save()` 是原子的(用 tmp + replace,不留 .tmp 残骸)

## 不测什么

- `MigrationRunner` 怎么用 `MigrationState` —— 在 `runner_modes/`
- 多进程并发写 —— memory.talk 单进程跑,没有这个 case

## fixture

只用 `tmp_path`,不挂任何项目级 fixture。
