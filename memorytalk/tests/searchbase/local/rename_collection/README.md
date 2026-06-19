# rename_collection — collection 改名

## 这个场景在测什么
admin.rename_collection 把一个 collection 改名:行数据保留、旧名释放;old 不存在时幂等 no-op。
启动会按 SCHEMAS 预建声明的集合,所以 rename 的目标 `new` 可能已作为**空占位**存在——这时
drop 掉空占位再 rename(把 old 的行带过去);若 `new` 已有真实行,则拒绝改名(no-op,不覆盖数据)。

## 不在这测什么
- 跨进程 / 远端 backend
