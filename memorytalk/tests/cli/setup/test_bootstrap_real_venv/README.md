# test_bootstrap_real_venv

**真 subprocess 集成测试。**跟其它 setup wizard 测试隔离。

## 场景

跟单元测试不同 —— 这个 case 真的拉两个 venv:

1. 在 `tmp_path/venv_a` 用 `python3 -m venv` 建一个**外层 venv**
2. 把当前 repo 的 memorytalk 用 `pip install <repo>` 装进 venv_a
3. 设 `HOME=tmp_path/home`,跑 `<venv_a>/bin/memory-talk setup` 起来
4. setup 检测自己**不在 `~/.memory-talk/.venv` 里**(`HOME` 已改) → 触发 bootstrap
5. setup 用 `MEMORYTALK_BOOTSTRAP_SOURCE=<repo>` 把 memorytalk 装进 `~/.memory-talk/.venv`(避开 PyPI,直接用本地源)
6. setup 调 `os.execv` 切到内层 venv 的 memory-talk
7. 内层 setup 重新跑,这次 `_already_in_venv()` 返回 True → 进入 wizard
8. wizard 在第一个 prompt 上 EOF → 报错退出(预期行为,我们不喂 wizard 应答)

## 验证

- `~/.memory-talk/.venv/bin/memory-talk` 存在(bootstrap 走通了)
- `~/.memory-talk/.venv/bin/python` 存在
- 整体流程在 timeout(默认 120s)内结束

## 为什么不验 setup 跑通的 wizard

bootstrap 是 thin orchestration over `subprocess.run + os.execv`,我们要确认的是
"切 Python 解释器这条路能跑";wizard 主流程已经在 in-process 测试里覆盖了。
跑完整 wizard 还要喂应答 + mock embedding probe,在 subprocess 边界搞这些
噪音大于价值。

## 性能

`pip install <repo>` 会拉所有 deps(lancedb, fastapi, ...),首次跑 ~30-90s。
之后 pip cache 加速到 ~10s 量级。慢但能接受 —— 整个测试套大部分还是 fast。
