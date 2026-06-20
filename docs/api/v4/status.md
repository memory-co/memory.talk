# Status API

**v4 与 v3 一致** —— `GET /v4/status` 的形态(健康检查 + 数据统计 + provider 信息,无 body)**完全照 v3**,本目录不复制。

**v4 唯一变化**:路由从 `/v3/status` 挪到 **`/v4/status`**。

> **注明 v4 语义差异**(字段不变,统计口径变):
> - `reviews_total` 在 v4 是 **vestigial `0`** —— v3 论坛 review(对整张卡的顶踩)已退役;v4 的表态落在 Position 上(`reviews` 表 target = `position_id`),不计入这个老字段。
> - `cards_total` 统计的是 **v4 卡**(`/v4/cards` 建的 Issue);v3 老卡已整体改名 `insight`,不进 `cards_total`。

> 完整字段表(`data_root` / `sessions_total` / `searches_total` / `recalls_total` / `embedding_*` / `sync_enabled` 等)见 [`../v3/status.md`](../v3/status.md)。
