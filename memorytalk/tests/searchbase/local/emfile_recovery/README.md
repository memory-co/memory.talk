# emfile_recovery — search 撞 EMFILE 后的自愈反应链

## 这个场景在测什么

LanceDB 在 fragment 数过多 + fd 配额吃紧时会从 `search` 路径里抛出
"Too many open files"。searchbase 不能让这个异常直冒到调用方 —— 它
要**在原地自愈**:走 Maintenance 的 `recover_from_emfile()`,做
compaction + 重连 LanceDB,然后调用方的 search 像没事一样返回。

具体性质:

1. **counter 推进**:每发生一次 EMFILE 自愈,`emfile_recoveries` +1,
   `last_emfile_at_iso` 写当前时间
2. **并发不重复做**:多个并发 search 同时撞 EMFILE,只**一次**真正的
   recovery 跑出来(generation counter 保护),其它 caller 在锁
   后面看到 generation 已经推进就跳过自己的恢复
3. **真换连接**:recovery 的关键步骤是关闭并重新打开 LanceDB
   connection ——`index.db` 在 recovery 后必须是一个**全新对象**
   (compaction 单独跑不释放进程持有的旧 fd,只有重连才行)
4. **known set 自刷新**:即使 recovery 进来时 `known_collections`
   set 是空的(degraded 启动场景),compact 之前先调
   `refresh_known_collections()` 拉取真实的表清单,这样有数据的
   collection 也能参与 compaction

## 为什么是单独场景

EMFILE 是一条**反应链**(search → 异常 → Maintenance.recover →
compact + reconnect → retry search),涉及锁 / generation counter /
连接管理,跟周期 compaction(主动维护)语义不同。混在一起会让两条
故事线挤在同一个 README。

## fixture 来源

- `index` —— 直接构造 `Maintenance` 调用 `recover_from_emfile()`
- `backend` —— 走 `LocalSearchBackend` 公开接口验证 known set 刷新
