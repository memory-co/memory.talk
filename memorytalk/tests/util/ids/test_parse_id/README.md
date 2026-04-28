# test_parse_id

`parse_id()` 把字符串 id 拆成 `(IdKind, raw)` 二元组,前缀不在白名单时抛
`InvalidIdError`。

## 场景矩阵

| 测试函数 | 输入 | 预期 |
|---|---|---|
| `test_parse_id_card` | `"card_01jz8k2m"` | `(IdKind.CARD, "01jz8k2m")` |
| `test_parse_id_session_link_search_event` | `sess_*` / `link_*` / `sch_*` / `evt_*` | 分别归到 SESSION / LINK / SEARCH / EVENT |
| `test_parse_id_rejects_unknown_prefix` | `"foo_bar"` | `InvalidIdError` |

## 覆盖的代码路径

- `util/ids.py::parse_id()`:前缀分发 + 抛 `InvalidIdError`
- `IdKind` 枚举的所有分支

## 为什么 `parse_id` 是单点

`api/log.py`、`api/view.py`、`SessionService._require_session()` 都靠这一个函数
做"拿到 id 字符串 → 知道该走 cards 还是 sessions"的分发。前缀错了应该立刻
400,而不是去 SQL 查个空集再误诊为 404。
