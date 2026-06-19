# v4_ids — pos_ 前缀 id

## 这个场景在测什么
v4 新增的 Position id(`pos_<ulid>`)能 mint、能被 `parse_id` 认成
`IdKind.POSITION`;card_ 等老前缀不受影响;未知前缀仍报 `InvalidIdError`。

## 不在这测什么
- card_ / sess- / review_ 的既有解析 → 既有 ids 测试
