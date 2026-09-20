# UI 基础组件

本目录采用 shadcn/ui 官方 New York 组件源码，使用 Radix primitives，兼容项目现有的 React 18 与 Tailwind CSS 3。源码来自 `https://ui.shadcn.com/r/styles/new-york/<组件名>.json`，许可证见 [LICENSE.md](LICENSE.md)。

业务页面统一从 `@/components/ui/*` 引用通用控件。工作树、认知对象和工作单元仍由业务组件组织；Markdown 与 ttyd 分别负责正文、终端渲染。

- `components.json` 声明组件风格、路径别名和 Tailwind 配置。
- `src/index.css` 的主题变量定义颜色与圆角；业务布局放在 `@layer components`，不覆盖全局按钮、输入框等原生元素。
- 按钮通过 `variant` / `size` 表达用途，弹窗使用 Dialog，破坏性确认使用 AlertDialog，移动导航使用 Sidebar 内置的 Sheet。
- 当前使用浅色主题。Sonner 直接使用应用主题，不引入 Next.js 或 next-themes。

本地适配包括中文无障碍文案、小屏弹窗尺寸、遮罩透明度，以及无 Trigger 的受控弹窗通过 `useDialogFocus` 恢复焦点。更新官方组件时需保留这些适配。

新增组件可以在前端目录执行 `npx shadcn@latest add <组件名>`。审查生成的源码与依赖，保持 React 18 / Tailwind 3 兼容；已经修改过的组件不要直接整体覆盖。
