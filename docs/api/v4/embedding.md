# Embedding API

**v4 与 v3 一致** —— embedding 配置 / 重算 / 健康检查的接口形态、请求 / 响应体**完全照 v3**,本目录不复制。

**v4 唯一变化**:相关路由统一挂到 **`/v4`** 前缀,行为不变。

> 注:v4 新增了 `cards`(embed issue)/ `positions`(embed claim)两个向量 collection;embedding 的 provider / model / dim 配置仍由同一套 `settings.json` 的 `embedding` 段管,重算行为不变(collection 清单见 [`../../structure/v4/settings.md`](../../structure/v4/settings.md))。

> 完整契约(配置项、重算触发、健康端点)见 [`../v3/embedding.md`](../v3/embedding.md)。
