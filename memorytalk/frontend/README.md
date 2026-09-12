# memory.talk 前端

前端采用与 shellbase 一致的技术栈：React 18、TypeScript、Vite、Tailwind CSS、Zustand、TanStack Query，UI 统一采用 shadcn/ui（New York / Radix）、Lucide、Sonner。Markdown 展示使用 react-markdown 与 remark-gfm，认知对象的元数据通过 YAML 解析。

## 页面组织

整个应用采用统一的 React Shell 和 hash 路由。左侧是工作导航，中央聚焦当前工作或认知内容，工作区右侧可按需打开认知库。终端与网页通过 iframe 展示；内部页面使用 React 组件，页面切换不会主动结束会话。

| 页面 | 功能 |
| --- | --- |
| 工作台 `#/` | 创建工作、继续最近的工作 |
| 工作区 `#/work/<id>` | 工作状态、子工作、会话创建与切换、终端窗口或快照、agent 对话记录、认知库侧栏 |
| 认知库 `#/library` | 按层浏览、全文搜索、对象阅读、版本历史、创建原文 / issue / card、编辑 card |
| 设置 `#/settings` | 选择与注册用户、查看运行环境和浏览器终端接入方式 |

侧栏使用 shadcn Sidebar，支持折叠，移动端使用带焦点管理的 Sheet 抽屉。`Ctrl/Cmd + B` 折叠侧栏，`Ctrl/Cmd + K` 搜索工作（方向键选择、Enter 打开），首页输入框按 Enter 创建工作、Shift + Enter 换行。身份、侧栏偏好和每个 work 选中的会话保存在本地。

## 开发与构建

在仓库根启动后端，然后启动前端开发服务器：

```bash
memory.talk server start
cd memorytalk/frontend
npm ci
npm run dev
```

Vite 默认将 `/api` 代理到 `http://127.0.0.1:8000`。其他地址可以通过环境变量指定：

```bash
MEMORY_TALK_API=http://127.0.0.1:8123 npm run dev
```

生产构建：

```bash
npm run build
```

构建会先进行 TypeScript 检查，再生成 `dist/`。后端启动时若发现构建产物，将在 `/` 托管页面、在 `/assets` 托管静态资源；构建完成后需重启此前已运行的后端。未构建前端时，后端 API 仍可独立运行。页面采用 hash 路由，直接链接或刷新页面无需服务端路由回退。

## 与后端的边界

- `api.ts` 统一处理响应信封、错误和 `X-Memory-Talk-User` / `X-Memory-Talk-Work` 请求头；服务端数据由 TanStack Query 管理。
- 认知对象按最新接口的 `files` / `content` 读取。标题来自路径末段；card 和 issue 的正文来自 `readme.md`，元数据来自 `meta.yaml`。界面派生阅读视图，保存时仍提交文件内容；编辑卡片正文和语境会保留已有的关联元数据。
- 自定义层提供通用文件阅读视图，具体校验由后端负责。当前未提供自定义层编辑器和 issue 论证编辑界面。
- 会话记录和终端快照按需轮询，切换页面后停止相应轮询。当前没有原生 agent 消息发送或流式推送接口，因此对话记录为阅读视图，交互在终端内完成。
- 配置 `MEMORY_TALK_TTYD_URL` 后可以嵌入浏览器终端；地址需对浏览器可访问，并支持 `?arg=<session_id>` 来连接同一 tmux socket。未配置时展示真实的终端快照与接入提示。
- 网页直接使用会话 URL，提供独立窗口入口；外部站点可能限制 iframe 嵌入。当前没有本地服务反向代理，浏览器必须能访问目标地址。

本机接入浏览器终端的示例（需要已安装 `tmux` 和 `ttyd`）：在一个终端运行以下命令，让 URL 参数作为 tmux 的目标会话传入。

```bash
ttyd -W -a -i 127.0.0.1 -p 7681 -- tmux -L memorytalk attach-session -t
```

在另一个终端设置地址并启动后端；若后端已运行，先停止旧进程再启动，使环境变量生效。

```bash
export MEMORY_TALK_TTYD_URL=http://127.0.0.1:7681
memory.talk server start
```

这里的 `memorytalk` 是默认 tmux socket 名称；自定义了 `MEMORY_TALK_TMUX_SOCKET` 时，两边应使用同一名称。`--` 用于分隔 ttyd 选项与 tmux 命令参数。

## 代码结构

```text
src/
├── shell/             # Shell、工作树、首页、工作区与会话展示
├── collections/       # 认知库、对象阅读、历史、创建与编辑
├── settings/          # 用户和环境设置
├── components/        # 业务通用展示、按需加载的 Markdown
│   └── ui/            # shadcn/ui 官方组件与本地适配
├── hooks/             # 移动断点、受控弹窗焦点恢复
├── lib/               # API、类型、查询、路由、偏好、文件阅读视图
└── index.css          # 全局样式与响应式布局
```

组件来源、主题与扩展约定见 [UI 基础组件](src/components/ui/README.md)。工作区、认知库和设置按路由延迟加载；工作搜索和 Markdown 按需加载。界面不会注入演示工作或模拟响应，加载、空数据和请求失败分别展示对应状态。
