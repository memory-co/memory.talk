# src —— 前端源码

React 18 + TypeScript + Vite + Tailwind + shadcn/ui。入口 `shell/main.tsx`:`AppProviders`(TanStack Query + Toaster)包着 `auth/Gate`,门后面才是 `shell/Shell`。hash 路由,状态分三处:服务端数据在 TanStack Query,登录态 / 语言 / 侧栏偏好在 zustand(`lib/store.ts`),当前页面在 URL(`lib/router.ts`)。

| 目录 | 是什么 |
|---|---|
| [`auth/`](auth/README.md) | 门:setup 页、登录页、决定显示哪个的 Gate |
| [`shell/`](shell/README.md) | 壳:侧栏、面包屑、首页、工作区(列 × 工作单元)、工作单元面板、全局搜索 |
| [`metas/`](metas/README.md) | 元认知页:文件目录 / 最近修改、一个文件一页(属性 + 正文)、按协议画表单 |
| [`settings/`](settings/README.md) | 设置:账号、团队成员、语言、环境 |
| [`components/`](components/README.md) | 通用件:Markdown 阅读、Milkdown 编辑器、Loading / Empty / Modal 等;`ui/` 是 shadcn 原件 |
| [`hooks/`](hooks/README.md) | 两个小 hook:移动断点、受控弹窗焦点恢复 |
| [`lib/`](lib/README.md) | API 客户端、类型、查询、路由、偏好、多语言、层协议工具 |
| `assets/` | `mark.svg` 图标 |
| `index.css` | Tailwind 入口 + shadcn 主题 token + Markdown 排版 + 终端输出 + Milkdown 主题变量映射;不写业务 class |

约定:布局全用工具类和 `components/ui` 拼,不写自定义 CSS 类;文案全走 `lib/i18n.ts`(英文是源字典,中文对照);前端不认识具体哪一层,认知层的一切形状来自后端协议。
