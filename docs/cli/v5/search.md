# search

综合搜索,对应 [`/api/search`](../../api/v5/search.md)。

```bash
memory.talk search 环境变量                 # 工作 / 元认知 / 成员各出一份
memory.talk search 环境变量 --limit 5       # 每种最多 5 条
memory.talk --json search 环境变量          # {"query", "hits", "counts"}
```

输出每行一条:`[work] <id>  <目标>  (<状态>)`、`[<层>] <对象路径>:<行号>  <命中的那一行>`、`[user] <名字>  <显示名>  <邮箱>`。
