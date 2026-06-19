# rename_collection — collection 改名

## 这个场景在测什么
admin.rename_collection 把一个 collection 改名:行数据保留、旧名释放;old 不存在或 new 已存在时幂等 no-op。

## 不在这测什么
- 跨进程 / 远端 backend
