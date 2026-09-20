# work_servers / http_worklet — 最薄的 server:窗是 URL,把手为空

## 这个场景在测什么
`https://` 由 http server 接:本地服务(localhost:port)的 `embed` 走 `/proxy/<port>/…`,外链原样;把手为空,
`rounds` 报 409(把手没有这个能力);永远 alive。

## 不在这测什么
- 真浏览器实例(将来的 webmuxd)

## fixture 来源
`client`。
