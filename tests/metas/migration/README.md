# metas / migration — 从 collections 改名过来的老数据

## 这个场景在测什么
2026-09-20 之前数据目录叫 `~/.memory.talk/collections/`,锚定文件叫 `collections.json`。改名后第一次起服务:目录搬到 `metas/`,
锚定文件在最底层提一次 `[origin] metas: rename collections.json to metas.json`,层清单、已有对象、历史都还在;第二次起不再重复提交。

## 不在这测什么
- 锚定文件本身的语义 → `config`

## fixture 来源
`home`(自己起两次 app,中间把数据改成老样子)。
