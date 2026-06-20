# settings.json

**v4 与 v3 一致** —— `~/.memory.talk/settings.json` 的路径、schema、各段(`server` / `vector` / `relation` / `embedding` / `search` / `sync` / `explore`)、wizard 写入 / 手工编辑语义**沿用 v3**,本目录不复制。

> 完整 schema(各字段类型 / 默认值 / 环境变量插值)见 [`../v3/settings.md`](../v3/settings.md)。setup wizard 见 [`../../cli/v4/setup.md`](../../cli/v4/setup.md)。

## v4 注明:向量 collections

v4 的 LanceDB 向量库在 v3 基础上**新增两个 collection**(为问题图检索服务):

| collection | embed 什么 | 来源 |
|---|---|---|
| `insights` | v3 老卡文本 | 沿用 v3(v3 `cards` 改名而来) |
| `rounds` | session 旁白 round | 沿用 v3 |
| `cards` | v4 卡的 `issue`(问题) | **v4 新增** |
| `positions` | v4 答案的 `claim` | **v4 新增** |

这只是 collection 清单的增量;`settings.json` 的 `embedding` / `vector` 配置段本身不变(同一套 provider / model / dim 管所有 collection)。磁盘布局速查见 [`filesystem.md`](filesystem.md)。
