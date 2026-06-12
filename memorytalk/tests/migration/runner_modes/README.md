# runner_modes

## 测什么

`MigrationRunner` 在拿到不同的 `(state, existing_install, handle)`
组合时的行为:

- **init_latest** —— state 空 + 不像旧装,只跑最新版的 `init_*`,且
  把所有早期版本也标成 applied(为下次升级铺平 catch_up)
- **upgrade_from_zero** —— state 空 + 像旧装,按版本顺序跑全部 `up_*`
- **catch_up** —— state 已有记录,只跑 highest_applied 之后的 `up_*`
- **子系统 handle 缺失** —— `admin=None` 时跳过 searchbase,只跑
  database;状态停留在 database,留给下次拿到 admin 的启动接着跑
- **单步崩溃** —— 中途 raise 时,已成功的步骤被持久化,raise 上抛 —
  下次 catch_up 从下一步接着跑

## 不测什么

- v1 内容本身做了什么(在 `v1_baseline/` / `v1_upgrade_from_081/`)
- `MigrationState` 的 JSON 写入(在 `state_persistence/`)
- 跟 FastAPI lifespan 的拼装(在 `lifespan_integration/`)

## fixture

`stub_pkg` —— 在 `tmp_path` 下临时铺一个合成的 `migrations` 包,
两个版本(`v1`/`v2`)× 两个 subsystem(`database`/`searchbase`)×
两个方法(`init`/`up`),每个 `run()` 都往一个共享 list 里 append
一个 tag,这样调用顺序可观测。**不**碰 `memorytalk.migrations` 真
内容 —— runner 行为跟版本数量、子系统数量无关,合成包让断言不依赖
真实迁移的副作用。
