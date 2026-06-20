# Session

**v4 与 v3 一致** —— session 的数据结构(`sessions` 表 + session 目录下的 `rounds.jsonl`)、字段语义、磁盘布局**沿用 v3**,本目录不复制核心契约。

> 完整结构(`sessions` 表列、`rounds.jsonl` 每行格式、cursor 三元组、`sess_` 前缀)见 [`../v3/session.md`](../v3/session.md)。

## v4 新增:session 目录下的 mark sidecar

v4 在 session 旁挂了**逐 round 注解**的派生层(抽 v4 卡的写路径前端):

- **`marks/` sidecar**:session 目录下新增 `marks/`,存逐 round 提交的注解(canonical file 罐)。
- **`session_marks` 表**:SQLite 派生索引,把 mark 拍平成可 join 的行(每条 mark 一行,带 `last_index` / 关联到的 `card_` 等)。

这层是 v4 专属、v3 没有;它不改 session 本体(`sessions` / `rounds.jsonl` 仍照 v3),只在旁边追加注解 + 由 `#…？` 自动建 v4 卡。

> 完整结构(`marks/` 罐格式、`session_marks` 表 schema、`m<n>` 寻址、与 `card_sessions` 的关系)见 [`session-mark.md`](session-mark.md);机制 / 设计推理见 [`../../works/v4/session-mark.md`](../../works/v4/session-mark.md)。
