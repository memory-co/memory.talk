# providers / local_fs — 文件系统型 provider 的原语

## 这个场景在测什么
`LocalFS` 对 `FileSystemProvider` 基类的实现:`write` 整体替换、`append` 追加、`read` / `exists` / `delete` / `list` / `stat`,
以及它独有的能力 `local_path`(能力要显式探,`has("local_path")`);路径不能越出根。

## 不在这测什么
- S3 / OSS(没有实现)
- 仓储怎么用它(`works/`、`users/`)→ `works/`、`users/` 各场景

## fixture 来源
`tmp_path`(pytest 自带);不起服务。
