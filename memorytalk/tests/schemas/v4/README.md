# v4 schemas — 模型 + 默认值

## 这个场景在测什么
Card / Position / CardLink / CardSession 读模型 + 4 个 create 请求模型的字段
默认值与类型约束:Position 计数默认 0、scope 默认空、无 credence 字段;
CardSession.position_id 默认 `""`;CardLink 带 target_type;
CreateReview.argument 限定 {-1,0,1}。

## 不在这测什么
- 持久化 round-trip → tests/repository/v4/
- credence 现算 → service plan
