# Works (v3)

机制 / pipeline / 设计决策。**做什么以及为什么** —— 不重复在其他三个目录里讲的"接口长什么样"。

## 四个目录的分工

| 目录 | 只放 | 不放 |
|---|---|---|
| [`../../cli/v3/`](../../cli/v3/) | 命令调用、flag 表、输出示例、退出码、推荐姿势 | schema 摘要、机制解释、跨命令时序 |
| [`../../api/v3/`](../../api/v3/) | endpoint 签名、请求/响应字段、status code、error shape | 算法描述、写入顺序、DAG 规则 |
| [`../../structure/v3/`](../../structure/v3/) | 对象 schema、存储位置、字段语义("是什么") | 写入路径、事件链、迁移、"为什么不存 X" |
| `works/v3/`(本目录) | pipeline、算法、设计决策 + 理由、多组件流程、不变量、设计史 | (catch-all) |

## 文档清单

| 主题 | 文档 |
|---|---|
| 论坛动力学(沉浮 + ranking 三轴) | [forum-dynamics.md](forum-dynamics.md) |
| Card 创建流程(rounds 展开 + source_cards DAG) | [card-creation-flow.md](card-creation-flow.md) |
| explore 先验/后验抽卡工作区(君子协定 + 焦点会话绑定 + 取代旧 cwd-explore，已设计未实施) | [explore.md](explore.md) |
| Card 删除流程(级联策略 + 不级联清单) | [card-deletion-flow.md](card-deletion-flow.md) |
| Recall pipeline(file canonical + dedup + 派生 recall_count) | [recall-pipeline.md](recall-pipeline.md) |
| Session ID 命名空间(canonical 算法 + raw 转换) | [session-namespace.md](session-namespace.md) |
| Hook 安装(setup STEPS pipeline + adapter 注册表) | [hook-installation.md](hook-installation.md) |
| Codex trust 流程(loop + rollback on abort) | [codex-trust-flow.md](codex-trust-flow.md) |
| Sync pipeline(watcher + checkpoint + cursor) | [sync-pipeline.md](sync-pipeline.md) |
| Search ranking(FTS + 向量 + 公式 + `--recall` 调试) | [search-ranking.md](search-ranking.md) |
| Search DSL 语法 | [dsl.md](dsl.md) |
| Session rounds 写入(append-only + LanceDB rounds 索引) | [session-rounds-write.md](session-rounds-write.md) |
| Review 怎么影响 card stats | [review-impact.md](review-impact.md) |
| Read 副作用(read_count + 事件) | [read-side-effects.md](read-side-effects.md) |
| 向量索引补齐 + EMFILE 恢复 | [index-backfill.md](index-backfill.md) |
| searchbase 通用搜索底座(SearchBackend 端口 + 命名实例 + auto_split 切块，已实施) | [searchbase-extraction.md](searchbase-extraction.md) |
| migration 模块(searchbase schema in-place 演化 + 0.8.1 兼容 baseline，已设计未实施) | [migration.md](migration.md) |
| File-canonical 模式(card/review/session/recall 共用) | [file-canonical-pattern.md](file-canonical-pattern.md) |
| Explore cwd suppression(hook 模式开关) | [explore-cwd-suppression.md](explore-cwd-suppression.md) |
