# fts_self_heal

## 测什么

FTS index 在盘上**残缺**(index 目录还在、manifest 里名字还占着,但
部分文件丢失 —— 0.8.x EMFILE 崩溃年代的典型遗留)时,searchbase 必须
能自愈,而不是每次 search 都 500:

- lance 4.0 对这种 index 的行为:`list_indices()` 打 WARN 然后**静默
  省略**它(返回里没有这个 index)→ 我们的检测会以为"没有 text
  index"
- 此时 `create_index(replace=False)` 会撞 "Index name 'text_idx'
  already exists" —— 这正是 1.0.0 线上事故的形状(0.8.1 用的是
  `replace=True`,每次启动悄悄重建,把损伤掩盖了;searchbase 重写时
  改成 False 引入回归)
- 断言:删掉 index 目录里的一个 tokens 文件后,重开 backend 再
  search,**不抛错**且 FTS 索引被重建、查询正常返回

## 不测什么

- index 文件是怎么坏的(EMFILE / 断电 / 半截写入)—— 那是上游
  lance 的写入原子性问题,我们只负责坏了之后能恢复
- `list_indices` 抛异常的路径 —— 那走 EMFILE recovery,在
  `emfile_recovery/`

## fixture

`data_root` + 本目录内自建 backend(要拿 `vectors_dir` 下的
`cards.lance/_indices/` 目录动手脚,所以不用共享 `backend` fixture
的 yield 形式,自己控制 close/reopen)。
