# Works (v4)

机制 / pipeline / 设计决策 —— **做什么以及为什么**。目录分工同 [v3](../v3/README.md)。

v4 是一次**大改代**,目前只立机制、未实施。它的由头是**卡的重新设计**:一张卡从「一句陈述」升级成「**对某个问题的一个回答**」,所有卡连成一张**被治理的问题图**(IBIS 结构 + 位 / 变治理)。v3 现有的那套卡同步**改名 `insight`、数据保留、慢慢下掉**,把 `card` 这个名字腾给 v4。

## 文档清单

| 主题 | 文档 |
|---|---|
| card 重新设计(问答化 + IBIS 问题图 + 位/变治理 + 写/读路径 + 与 insight 共存迁移,已设计未实施) | [card.md](card.md) |
| card IBIS 生命周期(一张卡从问题→答案→治理→召回的全流程;**问题客观从 mark、答案主观+引证**;把各机制串成时间线,已设计未实施) | [card-lifecycle.md](card-lifecycle.md) |
| session mark(以写代读的逐 round mark〔YAML 数组〕+ `#…？` 自动建卡/关联;mark = session 附属 `sess_xxx#n`,`card_source` 指 mark;card 写路径的前端,已设计未实施) | [session-mark.md](session-mark.md) |
| 交互式 `session mark` 的 TUI 方案(**消费者是 AI**:主路径=批量 `--mark`+结构化 `--json`,人路径=行式 REPL〔rich+questionary〕;**否决全屏 TUI**——转义序列对 AI 是负资产) | [session-mark-tui.md](session-mark-tui.md) |
| v3 card → insight 迁移(腾名 + 保数据:表 / LanceDB collection / `card_*` id 前缀改名,catch-up 原地升级,已设计未实施) | [insight-migration.md](insight-migration.md) |

> 接口层 [`docs/cli/v4/`](../../cli/v4/) / [`docs/api/v4/`](../../api/v4/) / [`docs/structure/v4/`](../../structure/v4/) 已起,记录命令 / 端点 / 数据结构契约;本目录(works)立机制与设计推理。
