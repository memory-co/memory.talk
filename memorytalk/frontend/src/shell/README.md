# shell —— 壳和工作区

| 文件 | 重点 |
|---|---|
| `main.tsx` | 入口:`AppProviders` → `Gate` |
| `Shell.tsx` | `Shell`:≥1024 用 shadcn sidebar-07,768–1023 图标栏,<768 `MobileShell`(侧栏 / 主区 / 元认知面板三个整屏吸附列)。`SidebarBody`(导航 + 工作树 + 底部账号)、`Crumbs`(面包屑:工作页显示目标;元认知页把打开的文件路径逐段拆进来,点中间一段跳到那个目录)、`Page`(按路由挑页面)、`ShellContent`、`useMediaQuery` |
| `TaskTree.tsx` | `TaskTree`:侧栏里的 work 树(`WorkRow` / `SubRow` / `StatusIcon`) |
| `Home.tsx` | `Home`:工作台首页,`WorkComposer`(建 work 的输入框,也给拆分子 work 用)、`NewSubwork`(弹窗) |
| `Workspace.tsx` | `Workspace`:一个 work 的页面——头部(目标 / 状态 / 拆分 / 添加一列),下面是画布:**几列,每列从上到下摆工作单元卡片**。`layout()` 把后端画布和工作单元清单对齐(没提到的工作单元补到第一列,没了的丢掉);`edit()` 整份 PUT 画布带 version,409 就重载;工作单元可收起、上下左右挪;列可收起成窄边,空了才能删;每列底部「添加工作单元」弹出 `NewWorklet`(弹层里像浏览器新标签页:上面一条地址栏,块即 URI;下面几块应用,点终端类直接用默认工作目录开,网页 / 自定义先把前缀填进地址栏),建好后 `placeNew` 挪到那一列 |
| `PanelView.tsx` | `PanelView`:一个工作单元的身体——终端(有 ttyd 就 iframe,否则快照轮询)/ agent 的对话记录 / 网页 iframe;复制地址、新窗口打开、重连、结束工作单元 |
| `GlobalSearch.tsx` | `GlobalSearch`:⌘K 弹窗,`GET /search` 按 kind 分组(工作 / 元认知 / 成员),点了就跳 |
