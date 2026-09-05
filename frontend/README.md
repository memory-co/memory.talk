# frontend(v5)

memory.talk v5 的前端骨架,技术栈照 shellbase `web/`:**Vite + React 18 + TypeScript + Tailwind + zustand + @tanstack/react-query**,多入口(shell + 各应用页),`/api`、`/tty`、`/proxy` 全部代理给后端。**目前全部是空文件,只立结构,不做实现。**

```
frontend/
├── package.json / vite.config.ts / tsconfig.json / tailwind.config.js / postcss.config.js
├── index.html                # Shell:task 树 + 画布
├── apps/                     # 各应用页(每个块里的 iframe 装的就是这些)
│   ├── files.html            #   file:// 文件浏览器 / 编辑器
│   ├── browser.html          #   https:// 浏览器面板
│   ├── settings.html
│   ├── cards.html            #   card 词条:目录、正文、历史
│   └── issues.html           #   issue 讨论页:立场、论证、图
├── public/login.html         # token 换 Cookie
└── src/
    ├── index.css
    ├── lib/
    │   ├── api.ts            #   后端 API 封装
    │   ├── grid.ts           #   24×16 网格剖分:分割 / 拖线 / 关闭回收
    │   ├── uri.ts            #   块的 URI 解析(协议 → 请求哪个 server;不维护协议名单)
    │   ├── store.ts          #   zustand
    │   ├── query.tsx / queries.ts   # react-query
    │   └── utils.ts
    ├── components/ui/        #   base-ui 封装(badge/button/card/dialog/dropdown-menu/input/label/sonner/tooltip)
    ├── shell/                # 顶层页面
    │   ├── main.tsx
    │   ├── Shell.tsx         #   画布:块 = iframe,布局只是 task 的视图
    │   ├── PanelView.tsx     #   单块 + 按需浮现的控制条
    │   ├── Dividers.tsx      #   可拖分割线
    │   ├── UrlBar.tsx        #   rich URL bar:recents + 应用宫格 + 自动补全
    │   ├── TaskTree.tsx      #   task 树侧栏:父子、状态、当前节点
    │   └── TaskHeader.tsx    #   当前 task:目标、状态、它管的 issue、拆 / 议 / 派
    ├── files/main.tsx
    ├── browser/main.tsx
    ├── settings/main.tsx
    ├── cards/
    │   ├── main.tsx
    │   ├── Catalog.tsx       #   目录(按目录分层的标题)
    │   ├── CardView.tsx      #   词条正文 + 链接 + 讨论页入口
    │   └── CardHistory.tsx   #   git log 视图
    └── issues/
        ├── main.tsx
        ├── IssueView.tsx     #   问题 + 立场 + 论证;manager、派出的 task
        └── IssueGraph.tsx    #   IBIS 边
```
