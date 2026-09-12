# collections / basic — 分层 git 的最小闭环:两层各放一个文件,stack 看到两个

## 这个场景在测什么
origin 层提交 `a/a.yaml`,issue 层提交 `a/b.yaml`;`stack` 的树里两个都在,而各层分支只有自己的那个。
这是 collections 机制的地基(层即分支、stack 是并集视图),别的场景都建立在它成立之上。直接走 `Repo`,不经 API、不经 schema。

## 不在这测什么
- 后缀规则 / 归属守卫 → `layer_guard`
- 对象 CRUD、历史、检索 → 同级其他场景

## fixture 来源
`svc`(取 `svc.collections.repo`)。
