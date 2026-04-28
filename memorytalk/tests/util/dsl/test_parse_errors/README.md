# test_parse_errors

`parse()` 的拒绝路径 —— 语法不完整、未知字段、IN 但语法不对。

## 场景矩阵

| 测试函数 | 输入 | 预期 |
|---|---|---|
| `test_parse_truncated_predicate` | `tag = ` | `DSLError` —— 等号右边缺值 |
| `test_parse_unknown_field` | `unknown = "x"` | `DSLError` —— 字段不在白名单 |
| `test_parse_in_without_list` | `tag IN "x"` | `DSLError` —— `IN` 后必须跟 `(...)` |

## 覆盖的代码路径

- `util/dsl.py::DSLError` 抛出点
- 字段白名单校验(防止 SQL 注入面变大)
- `IN` 操作符语法校验

## 为什么把错误集中到一个 case 里

错误路径都靠 `pytest.raises(DSLError)` 校验,逻辑同质化。放一起读起来一眼能看出
"这些都是非法输入"。再细分会让目录数膨胀但收益很低。
