# shell —— 壳和工作区

| 文件 | 重点 |
|---|---|
| `main.tsx` | 入口:`AppProviders` → `Gate` |
| `Shell.tsx` | `Shell`:≥1024 用 shadcn sidebar-07,768–1023 图标栏,<768 `MobileShell`(侧栏 / 主区 / 动态面板三个整屏吸附列)。`SidebarBody`(导航 + 工作树 + 底部账号)、`Crumbs`(面包屑:工作页显示目标;元认知页把打开的文件路径逐段拆进来,点中间一段跳到那个目录)、`Page`(按路由挑页面)、`ShellContent`(工作页右侧可开「动态」面板)、`useMediaQuery` |
| `TaskTree.tsx` | `TaskTree`:侧栏里的 work 树(`WorkRow` / `SubRow` / `Lead`);每行悬停出「⋯」(`RowActions`),点开是这个 work 的操作菜单:「拆分工作」(弹 `NewSubwork`)、「归档」/「改回运行中」(PATCH status) |
| `Home.tsx` | `Home`:工作台首页,`WorkComposer`(建 work 的输入框,也给拆分子 work 用)、`NewSubwork`(弹窗) |
| `WorkEvents.tsx` | `WorkEvents`:工作页右侧的「动态」面板——这个 work 的事件时间线(`GET /works/{id}/events`,5 秒刷新,新的在上):创建、状态变化、冻结、加 / 改别名 / 删列(`column.*`)、打开 / 挪动 / 关闭工作单元(`worklet.*`);画布事件按事件里的列标记写成 `列 3 · 别名`(当时的别名),`worklet.moved` 分换列(从 列 a 挪到 列 b)和同列换位(挪到第 n 个);每条下面一行是 `by · 时间`;事件里没有 URI(旧的关闭 / 挪动事件)就往前找同 id 的打开事件拿;认不出的 type 原样显示 |
| `Workspace.tsx` | `Workspace`:一个 work 的页面——头部(目标;拆分、归档在侧栏每行的「⋯」里),下面是画布:**几列,每列从上到下摆工作单元卡片**。`layout()` 把后端画布和工作单元清单对齐(没提到的工作单元补到第一列,没了的丢掉);布局改动**一个动作一个请求**(`op`:加列 `POST /columns` 带 beside + side、改别名 / 收起列 `PATCH /columns/{c}`、删列 `DELETE /columns/{c}`、挪 `POST /worklets/{w}/move` 带 column + index、收起工作单元 `PATCH /worklets/{w}`),成功就用交回的画布替换并刷新动态,失败提示并重拉画布;工作单元可收起、上下左右挪;列可收起成窄边,空了才能删;列标题是 `列 <编号>` / `列 <编号> · <别名>`(编号来自列 id,不按位置),点一下就地改别名(`ColumnName`,编号不动,清空就只剩 `列 <编号>`);每列底部一排:左边加一列 / 添加工作单元 / 右边加一列;「添加工作单元」弹出 `NewWorklet`(弹层里像浏览器新标签页:上面一条地址栏,块即 URI;下面几块应用,点一块只是把 URI 填进地址栏,回车或「打开」才建),建时带上 `column`,直接进那一列 |
| `PanelView.tsx` | `PanelView`:一个工作单元的身体——终端(iframe 装 tmuxd 交回的 ttyd 地址)/ agent 的对话记录 / 网页 iframe;复制地址、新窗口打开、重连、结束工作单元 |
| `GlobalSearch.tsx` | `GlobalSearch`:⌘K 弹窗,`GET /search` 按 kind 分组(工作 / 元认知 / 成员),点了就跳 |
