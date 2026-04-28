# test_card_invalid_indexes

`memory-talk card <json>` 场景测试 —— 非法的 `indexes` 或 `session_id` 必须
**拒绝入库**,CLI 以非零 exit code 退出,stdout 打印结构化 JSON 错误而不是
traceback,且 SQLite 里 cards 表**不增加行**。

## 场景矩阵(parametrize)

| `indexes` | 预期错误包含 | 拒绝原因 |
|---|---|---|
| `"1-99"` | `"out of range"` | 索引越过 session round 总数 |
| `"5,3"` | `"monotonically increasing"` | 列表非严格递增 |
| `"abc"` | `"bad index"` | 无法 parse 为整数 |
| `"5-2"` | `"not ascending"` | 区间端点 ai > bi |
| `"  "` | `"empty indexes"` | 去空白后为空 |

额外两个非 indexes-shape 的错误用例(单独测试,不 parametrize):

- `test_card_rejects_missing_session` —— session_id 前缀正确但对象不存在
- `test_card_rejects_bad_session_prefix` —— session_id 不以 `sess_` 开头

## 关键断言(每个 case 都检)

1. **`exit_code != 0`** —— CLI 必须非零退出
2. **stdout 是可 parse 的 JSON** —— 格式化错误而不是 traceback
3. **JSON 里有 `error` 字段** —— 错误可被机器读取
4. **error 包含期望子串** —— 错误文案能定位原因
5. **cards.count() 前后不变** —— 事务性:失败时零副作用

这第 5 条很关键:service 里 `parse_indexes` / 对 session / 对 round 的
**所有校验都在 SQLite 写入之前完成**,确保"哪怕校验失败了,也绝不会有 card
文件、SQLite row、LanceDB 向量或事件落地"。任何一条失守就会在这里被抓住。

## 覆盖的路径

- Click argument parsing + JSON body 解析
- `CardService.create()` 校验分支:
  - `parse_indexes()` 的各种异常(bad range / bad index / empty / non-monotonic)
  - index 越界检查
  - session 存在性检查
  - session_id 前缀检查
- `CardServiceError` → FastAPI 400 → `ApiError` → CLI `{error: ...}` + exit 1
- **事务性**:失败不留痕(assert count 不变)

## 和 valid scenario 的关系

- 同一份 `cli_env` fixture(`tests/cli/conftest.py`)
- 不同 scenario 目录,pytest `tmp_path` 隔离
- 先补 valid(确认快乐路径通),再补 invalid(反向验证)
