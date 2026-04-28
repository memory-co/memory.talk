# test_layout

`Config` 的路径属性 + `ensure_dirs()` 副作用 —— data_root 下应该有哪些子目录。

## 场景矩阵

| 测试函数 | 验证什么 |
|---|---|
| `test_default_data_root_layout` | `data_root / db_path / vectors_dir / sessions_dir / cards_dir / links_dir / search_log_dir` 名字和位置都正确 |
| `test_ensure_dirs_creates_expected_layout` | `cfg.ensure_dirs()` 后 5 个子目录都存在 |

## 覆盖的代码路径

- `config.py::Config.__init__`(data_root 解析)
- `Config.db_path` / `vectors_dir` / `sessions_dir` / `cards_dir` / `links_dir` / `search_log_dir` 属性
- `Config.ensure_dirs()` 创建所有必需目录

## 为什么 search_log 在 logs/search/ 而不是 search_log/

Settings 默认布局把"日志类"放 `logs/`,搜索审计是日志的一种;跟 sessions/cards
这种"对象"区分开。改路径就要改这条断言,提醒后来人。
