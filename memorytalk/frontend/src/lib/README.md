# lib —— 客户端基础

| 文件 | 重点 |
|---|---|
| `api.ts` | `api<T>(path, {method, body, work, signal, keepalive})`:统一加 `Authorization: Bearer`(来自 store)和 `X-Memory-Talk-Work`,解 `{data, message}` 信封,错误变 `ApiError(message, status, code)`。门说的话直接改登录态:409 `setup_required` → 标记要 setup;401 → 清登录态。`keepalive` 给关页面时还要发出去的请求(离开 work):sendBeacon 带不了 `Authorization`,只能 fetch keepalive。`pathPart()` 逐段 encode 路径 |
| `store.ts` | `usePreferences`(zustand + persist):`user` / `role` / `token` / `setupRequired`(不落盘)/ `collapsed` / `worklets`(每个 work 选中的工作单元)/ `locale`;`setSession` / `clearSession`(名字留着给登录页预填)/ `setLocale` … |
| `router.ts` | hash 路由:`Route{page, work, filter, layer, path, file, dir}`,`useRoute()` / `navigate(route)` |
| `queries.ts` | 常用查询 hook:`useWorks` / `useWork`(15 秒一次,兼作「在看」的心跳)/ `useUsers` / `useServers` / `useSystem` / `useLayers` / `useTrace`(`['trace', id]`,一个 work 的轨迹,5 秒刷新) |
| `query.tsx` | `queryClient`(4xx 不重试)和 `AppProviders` |
| `types.ts` | 后端模型的 TS 形状(`Work`(带 `viewers`)/ `Worklet`(带 `column` / `position` / `collapsed`)/ `Column` / `User` / `Layer` / `TreeView` / `RecentPage` / `SearchResult` …;轨迹是 OTLP/JSON 的 `WorkTrace` / `TraceSpan` / `TraceLogRecord` / `KeyValue`)和几个工具函数(`statusLabel` / `layerLabel` / `workletLabel` / `dateLabel` / `flattenWorks`;`attrValue` 从 OTLP 属性里取值,`intValue` 转成 number) |
| `i18n.ts` | 多语言:`en` 是源字典(`Key = keyof typeof en`),`zh` 逐键对照;`useT()` hook、模块级 `t()`、`localeTag()` |
| `protocol.ts` | 层协议工具:`FieldSpec` / `FileKind` / `Protocol` 类型;`splitFile` / `joinFile`(frontmatter ⇄ 字段 + 正文)、`toRegExp`(`(?P<name>` → JS 命名组)、`kindOf(protocol, rel)`、`instantiate(kind, name)`、`emptyValue` / `normalize`(表单值 ⇄ 写进 frontmatter 的值) |
| `utils.ts` | `cn()`(clsx + tailwind-merge) |
