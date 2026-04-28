# test_parse_basics

`util.dsl.parse()` 的基本语法 —— 空输入、单个 `=` 谓词、`AND` 链。

## 场景矩阵

| 测试函数 | 输入 | 验证什么 |
|---|---|---|
| `test_parse_empty` | `""` 和 `"   "` | 空/纯空白 → `[]`,不报错 |
| `test_parse_equal_string` | `source = "claude-code"` | 解析出 1 条 `Predicate(field, op="=", value)` |
| `test_parse_and_chain` | `tag = "decision" AND source = "claude-code"` | `AND` 把两个谓词串成 list,顺序保持 |
| `test_parse_source_field` | `source = "codex"` | `source` 字段在白名单里(不会被当 unknown 拒绝) |

## 覆盖的代码路径

- `util/dsl.py::parse()` 主流程
- 字符串字面量解析
- `AND` 分隔符
- `field` 白名单查表

## 为什么这是 dsl/ 而不是 cli/

`util.dsl` 是纯函数库,不需要 FastAPI/服务/数据库 —— 直接 import + assert 即可。
跟 cli/ 的相同点是:**每个测试场景一个目录 + README** 来记录"这一组在测什么"。
