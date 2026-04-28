# test_parse_reltime

时间字段(`created_at` / `expires_at`)的相对时间字面量,如 `-7d`。

## 场景矩阵

| 测试函数 | 输入 | 验证什么 |
|---|---|---|
| `test_parse_reltime_days_ago` | `created_at > -7d`(`now=2026-04-22T12:00Z`) | `value` 被解析成 7 天前的 ISO 时间字符串,以 `2026-04-15` 开头 |

## 覆盖的代码路径

- `util/dsl.py::parse(now=...)` 测试时把 `now` 注入(避免依赖系统时间)
- `-Nd` 字面量 → `now - timedelta(days=N)` → ISO8601 字符串

## 为什么固定 NOW

DSL 把 `-7d` 转成绝对时间戳是发生在**解析阶段**,而不是查询阶段。如果不固定 `now`,
测试在跨日运行时会偶发失败。靠注入参数,断言能盯死字符串前缀。
