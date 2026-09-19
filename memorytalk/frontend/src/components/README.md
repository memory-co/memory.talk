# components —— 通用件

| 文件 | 重点 |
|---|---|
| `Shared.tsx` | `Logo` / `UserAvatar` / `Loading` / `ErrorState`(带重试)/ `Empty`(空状态)/ `Modal`(受控 Dialog,带焦点恢复)/ `Markdown`(懒加载的阅读器)/ `safeWindowUrl`(只放行 http(s) 的 iframe 地址) |
| `Markdown.tsx` | `Markdown`:react-markdown + remark-gfm 的只读渲染,给对话记录等用 |
| `MarkdownEditor.tsx` | 默认导出:Milkdown Crepe 的包装——非受控,挂载时用 `value` 初始化、之后只往外报 `onChange`;`readOnly` 就是阅读视图(元认知页读写都用它,渲染一致)。关掉 Latex / AI,只读时再关掉块手柄 / 工具栏 / 占位符。主题变量在 `index.css` 里映射到 shadcn token。体积大,`Library.tsx` 挂载时预取 |
| [`ui/`](ui/README.md) | shadcn/ui 官方 New York 组件源码 + 本地适配 |
