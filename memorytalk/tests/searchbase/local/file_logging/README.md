# file_logging — 三类操作各自落独立文件

## 这个场景在测什么

searchbase 把自己的运行轨迹分三类写到三个独立文件,而不是一锅
端到一个全局日志里:

| 类别 | 文件 | 触发点 |
|---|---|---|
| 维护 | `maintenance.log` | `Maintenance.compact_all` / EMFILE 恢复 |
| 查询 | `query.log` | `LocalSearchBackend.search()` |
| 索引 | `index.log` | `upsert` / `delete` / `delete_where` |

具体性质:

1. **setup 创建三个文件**:`setup_file_logging(log_dir)` 接线后,三个
   logger 各自 info 一行就生成对应文件
2. **setup 幂等**:重复调不叠 handler(同 log_dir 同 category 只一份),
   否则长跑 server / 测试套件会泄漏 handler 然后每条 log 写 N 次
3. **不冒泡 stdout**:`propagate=False`,这些日志**不进**全局 logger /
   pytest caplog —— `tail -f` 是预期的查看方式,console 不被刷屏
4. **路由正确**:`backend.search()` 只写 `query.log`,`upsert` 只写
   `index.log`,`compact_all` 只写 `maintenance.log`;**互不污染**
   (同样的 logger 树底下不会互相串)

## fixture 隔离

Python 的 logger registry 是进程级单例。这个场景每个测试用一个新的
`tmp_path`,所以测试间必须**主动清理**已经接上的 handler —— 否则
idempotency 检查见到旧 handler 就会跳过新 setup,导致新测试的
log 文件永远是空的。

`_drop_searchbase_handlers()` + `_isolate_searchbase_handlers` autouse
fixture 处理这件事(before + after 双向清),让每个测试都是干净起步,
也不会泄漏给其它测试文件。

## fixture 来源

- `backend_with_logs` —— 这个场景自己的 fixture(`tmp_path` + 自定义
  `log_dir`,不复用 conftest 的 `backend`)
- `_isolate_searchbase_handlers` —— 这个场景自己的 autouse 隔离 fixture
