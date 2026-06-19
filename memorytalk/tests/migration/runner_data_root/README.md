# runner_data_root — 迁移拿到 data_root

## 这个场景在测什么
迁移 run() 接受 runner 传入的 data_root 关键字参数(为 v3 的文件目录 move 铺路);v1/v2 忽略它。

## 不在这测什么
- 实际文件 move(v3 迁移)
