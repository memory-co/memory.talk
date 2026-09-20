# Search API

综合搜索。一个入口,后端的 `SearchService` 把同一个 `q` 交给每个 service 的 `search()`(work / metas / users),把各家的命中汇总成一份。加一种可搜的东西 = 那个 service 实现 `search(q, limit)`,再在 `SearchService` 登记一行。

## GET /api/search?q=&limit=20

```json
{"query": "环境变量",
 "hits": [
   {"kind": "work", "id": "work_…", "title": "把配置改成环境变量", "snippet": "doing", "status": "doing"},
   {"kind": "meta", "id": "memory.talk/配置/该走文件还是环境变量", "title": "该走文件还是环境变量", "layer": "issue",
    "file": "memory.talk/配置/该走文件还是环境变量.issue/positions/只用环境变量.md", "line": 1, "snippet": "够用"},
   {"kind": "user", "id": "alice", "title": "环境变量爱好者", "snippet": "alice@example.com"}],
 "counts": {"work": 1, "meta": 3, "user": 1}}
```

| kind | 怎么搜 | 顺序 | 额外字段 |
|---|---|---|---|
| `work` | 目标(`goal`)含 q,大小写不敏感 | 新的在前 | `status` |
| `meta` | `git grep -i` 整个 `stack`,一行一条,命中折回对象;`metas.json` / `manager.json` 不算 | grep 的顺序 | `layer` / `file` / `line` |
| `user` | 名字 / 显示名 / 邮箱含 q | 按活跃 | — |

`hits` 按 kind 分组(work → meta → user);`limit`(1–100)是**每种**各最多几条,`counts` 是截断前各命中几条。`q` 为空 → 422。没有向量库、没有索引。
