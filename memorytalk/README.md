# memorytalk —— Python 包

pip 包 `memorytalk`,命令 `memory.talk`(也可 `python -m memorytalk`)。一个包装三样东西:

| 目录 / 文件 | 是什么 |
|---|---|
| [`backend/`](backend/README.md) | FastAPI 服务:models / services / controllers 三层 + work_servers;起来就是 `memory.talk server start` |
| [`cli/`](cli/README.md) | 命令行:本地 API 的客户端,不含业务逻辑 |
| [`frontend/`](frontend/README.md) | React 前端;`npm run build` 出的 `dist/` 随包分发,由后端在 `/` 托管 |
| `__init__.py` | `__version__`(`_from_pyproject()` 从 pyproject.toml 读,装好的包读 metadata) |
| `__main__.py` | `python -m memorytalk` → `cli.main()` |

设计在 [`docs/designs/v5`](../docs/designs/v5/README.md),端点在 [`docs/api/v5`](../docs/api/v5/README.md),命令在 [`docs/cli/v5`](../docs/cli/v5/README.md),测试在仓库根 `tests/`。
