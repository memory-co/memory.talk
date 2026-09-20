# services/search —— 综合搜索

`SearchService(works, metas, users)`:自己不搜,把同一个 `q` 交给每个 service 的 `search(q, limit)`,把各家的 `SearchHit` 拼成一个 `SearchResult`。`sources` 的顺序就是结果里分组的顺序(工作 → 元认知 → 成员);`counts` 是截断前的各家命中数。

要让一种东西可搜,只需它的 service 提供 `search(q, limit) -> list[SearchHit]`,然后加进 `sources`。现在:`WorkService.search`(目标含 q)、`MetasService.search`(git grep 全文)、`UserService.search`(名字 / 显示名 / 邮箱)。
