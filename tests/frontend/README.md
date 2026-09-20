# 前端托管

验证已构建页面和资源可访问，API 路由保持独立，未构建前端时 API 服务仍可运行。不依赖本机已存在的前端产物，也不创建 work 或工作单元。

```bash
pytest tests/frontend
```

页面构建检查在 `memorytalk/frontend` 执行 `npm run build`。浏览器验证应使用独立的 `MEMORY_TALK_HOME`，覆盖工作创建、子工作、工作单元切换、认知库读写与历史、用户选择及移动端导航；浏览器终端交互需要已接入 ttyd。

## 浏览器交互回归

`browser_smoke.py` 启动临时后端，使用独立数据目录、随机端口和 tmux socket；结束时清理进程与数据。需要已安装项目依赖、tmux 和 Python Playwright。可以使用系统 Chromium，或通过 `MEMORY_TALK_TEST_CHROMIUM` 指定浏览器路径；没有系统 Chromium 时使用 Playwright 安装的 Chromium。

```bash
npm --prefix memorytalk/frontend run build
python -m pip install playwright
python -m playwright install chromium
python tests/frontend/browser_smoke.py
```

覆盖工作与子工作创建、Select 状态切换、多个工作单元的键盘切换、认知库读写与版本历史、用户偏好、Command 搜索、移动端导航、弹窗焦点圈定与恢复，以及删除失败时保留确认框。使用真实后端，故障场景通过浏览器请求拦截模拟。截图目录会输出到终端。
