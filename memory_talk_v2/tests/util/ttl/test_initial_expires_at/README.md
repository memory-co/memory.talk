# test_initial_expires_at

`initial_expires_at(initial, now)` —— 创建对象时根据配置里的 `initial` TTL 算出
首次 `expires_at` 字符串。

## 场景矩阵

| 测试函数 | 输入 | 预期 |
|---|---|---|
| `test_initial_expires_at_math` | `initial=3600`,`now=固定` | 解析回来与 `now` 之差正好 3600 秒 |

## 覆盖的代码路径

- `util/ttl.py::initial_expires_at()`:`now + timedelta(seconds=initial)` → ISO8601
- 与 `iso_to_dt` 的反序列化对账,确保 round-trip 不丢精度

## 为什么不再多 case

`initial_expires_at` 是单分支函数,只有"加偏移再格式化",再多 case 会变成测
`datetime` 标准库本身。
