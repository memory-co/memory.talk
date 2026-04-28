# test_standard_mode_errors

`install_mode` 选 `1`(standard)时,setup 报错并 exit 1 —— pip 包还没发布,
标准模式实现暂未完成。

## 应答

| 步骤 | 应答 |
|---|---|
| install_mode | `1` |

## 验证

- `result.exit_code == 1`
- stderr 含 `not implemented` / 提示走 `[2]`
- `settings.json` **不存在**(报错前没写)
