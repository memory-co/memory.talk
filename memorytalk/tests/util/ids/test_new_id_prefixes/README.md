# test_new_id_prefixes

`new_card_id` / `new_link_id` / `new_search_id` / `new_event_id` 都按
`<prefix>_<ULID>` 形式产出 ID,且不会撞。

## 场景矩阵

| 测试函数 | 验证什么 |
|---|---|
| `test_new_card_id_has_prefix` | `new_card_id()` 以 `card_` 开头,总长 = 前缀 + 26 (ULID) |
| `test_new_link_id_has_prefix` | `new_link_id()` 以 `link_` 开头 |
| `test_new_search_and_event_have_prefixes` | `new_search_id()` → `sch_*`,`new_event_id()` → `evt_*` |
| `test_ids_are_unique` | 连发 1000 次 `new_card_id()`,集合去重后还是 1000 |

## 覆盖的代码路径

- `util/ids.py`:`new_*_id()` 系列函数
- ULID 生成 + 前缀拼接
- 唯一性靠 ULID 本身的时间戳 + 80bit 随机性

## 为什么验长度而不是验正则

ULID 自带字符集约束(Crockford base32),靠 `len == 26` 即足以发现意外截断。
真要验字符集会变成在测 ULID 库的实现,不是这层应该承担的事。
